from flask import Flask, render_template, request, jsonify
from bson import ObjectId
from models import Node, Task, Log
from riscv_emulator import RISCVEmulator, simulate_cpu_usage, simulate_memory_usage, get_system_info
from config import SECRET_KEY
import json

app = Flask(__name__)
app.secret_key = SECRET_KEY


class JSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, ObjectId):
            return str(obj)
        return super().default(obj)


app.json_encoder = JSONEncoder


def serialize_doc(doc):
    """Convert MongoDB document to JSON-serializable dict."""
    if doc is None:
        return None
    doc['_id'] = str(doc['_id'])
    if 'node_id' in doc and doc['node_id']:
        doc['node_id'] = str(doc['node_id'])
    if 'task_id' in doc and doc['task_id']:
        doc['task_id'] = str(doc['task_id'])
    if 'created_at' in doc:
        doc['created_at'] = doc['created_at'].isoformat()
    if 'completed_at' in doc and doc['completed_at']:
        doc['completed_at'] = doc['completed_at'].isoformat()
    if 'timestamp' in doc:
        doc['timestamp'] = doc['timestamp'].isoformat()
    return doc


# ============ Pages ============

@app.route('/')
def index():
    return render_template('index.html')


@app.route('/nodes')
def nodes_page():
    return render_template('nodes.html')


@app.route('/tasks')
def tasks_page():
    return render_template('tasks.html')


@app.route('/logs')
def logs_page():
    return render_template('logs.html')


# ============ Node APIs ============

@app.route('/api/nodes', methods=['GET'])
def get_nodes():
    nodes = Node.get_all()
    # Update usage stats for running nodes
    for node in nodes:
        if node['status'] == 'running':
            Node.update_usage(
                node['_id'],
                simulate_cpu_usage(),
                simulate_memory_usage(node['memory_mb'])
            )
    nodes = Node.get_all()
    return jsonify([serialize_doc(n) for n in nodes])


@app.route('/api/nodes', methods=['POST'])
def create_node():
    data = request.json
    name = data.get('name', 'Node')
    memory_mb = data.get('memory_mb', 512)
    cpu_cores = data.get('cpu_cores', 1)
    
    node = Node.create(name, memory_mb, cpu_cores)
    Log.create(str(node['_id']), None, f"Node '{name}' created", 'info')
    return jsonify(serialize_doc(node)), 201


@app.route('/api/nodes/<node_id>', methods=['GET'])
def get_node(node_id):
    node = Node.get_by_id(node_id)
    if not node:
        return jsonify({'error': 'Node not found'}), 404
    return jsonify(serialize_doc(node))


@app.route('/api/nodes/<node_id>/start', methods=['POST'])
def start_node(node_id):
    node = Node.get_by_id(node_id)
    if not node:
        return jsonify({'error': 'Node not found'}), 404
    
    Node.update_status(node_id, 'running')
    Node.update_usage(node_id, simulate_cpu_usage(), simulate_memory_usage(node['memory_mb']))
    Log.create(node_id, None, f"Node '{node['name']}' started", 'info')
    
    return jsonify({'status': 'running'})


@app.route('/api/nodes/<node_id>/stop', methods=['POST'])
def stop_node(node_id):
    node = Node.get_by_id(node_id)
    if not node:
        return jsonify({'error': 'Node not found'}), 404
    
    Node.update_status(node_id, 'stopped')
    Node.update_usage(node_id, 0, 0)
    Log.create(node_id, None, f"Node '{node['name']}' stopped", 'info')
    
    return jsonify({'status': 'stopped'})


@app.route('/api/nodes/<node_id>', methods=['DELETE'])
def delete_node(node_id):
    node = Node.get_by_id(node_id)
    if not node:
        return jsonify({'error': 'Node not found'}), 404
    
    Log.create(node_id, None, f"Node '{node['name']}' deleted", 'warning')
    Node.delete(node_id)
    return jsonify({'status': 'deleted'})


# ============ Task APIs ============

@app.route('/api/tasks', methods=['GET'])
def get_tasks():
    tasks = Task.get_all()
    return jsonify([serialize_doc(t) for t in tasks])


@app.route('/api/tasks', methods=['POST'])
def create_task():
    data = request.json
    name = data.get('name', 'Task')
    code = data.get('code', '')
    node_id = data.get('node_id')
    
    task = Task.create(name, code, node_id)
    Log.create(node_id, str(task['_id']), f"Task '{name}' created", 'info')
    return jsonify(serialize_doc(task)), 201


@app.route('/api/tasks/<task_id>/run', methods=['POST'])
def run_task(task_id):
    try:
        # Get task from collection directly
        from models import tasks_collection
        task = tasks_collection.find_one({'_id': ObjectId(task_id)})
        
        if not task:
            return jsonify({'error': 'Task not found'}), 404
        
        # Safely get node_id from request or task
        node_id = None
        try:
            data = request.get_json(silent=True) or {}
            node_id = data.get('node_id')
        except:
            pass
        if not node_id:
            node_id = task.get('node_id')
        
        if not node_id:
            # Find an available running node
            nodes = Node.get_all()
            running_nodes = [n for n in nodes if n['status'] == 'running']
            if not running_nodes:
                return jsonify({'error': 'No running nodes available. Please start a node first.'}), 400
            node_id = str(running_nodes[0]['_id'])
        
        node = Node.get_by_id(node_id)
        if not node:
            return jsonify({'error': 'Node not found'}), 404
        
        if node['status'] != 'running':
            return jsonify({'error': 'Node is not running. Please start the node first.'}), 400
        
        # Execute on RISC-V emulator
        Task.assign_node(task_id, node_id)
        Log.create(node_id, task_id, f"Task '{task['name']}' started on node '{node['name']}'", 'info')
        
        emulator = RISCVEmulator(node_id, node['memory_mb'])
        result = emulator.execute(task['code'])
        
        if result['success']:
            Task.update_status(task_id, 'completed', result['output'])
            Node.increment_tasks(node_id)
            Log.create(node_id, task_id, f"Task '{task['name']}' completed successfully", 'success')
        else:
            Task.update_status(task_id, 'failed', '', result['error'])
            Log.create(node_id, task_id, f"Task '{task['name']}' failed: {result['error']}", 'error')
        
        return jsonify({
            'status': 'completed' if result['success'] else 'failed',
            'output': result['output'],
            'error': result['error'],
            'registers': result['registers']
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ============ Log APIs ============

@app.route('/api/logs', methods=['GET'])
def get_logs():
    logs = Log.get_recent(100)
    return jsonify([serialize_doc(l) for l in logs])


# ============ Dashboard Stats ============

@app.route('/api/stats', methods=['GET'])
def get_stats():
    nodes = Node.get_all()
    tasks = Task.get_all()
    
    running_nodes = len([n for n in nodes if n['status'] == 'running'])
    total_tasks = len(tasks)
    completed_tasks = len([t for t in tasks if t['status'] == 'completed'])
    pending_tasks = len([t for t in tasks if t['status'] == 'pending'])
    
    total_memory = sum(n['memory_mb'] for n in nodes)
    used_memory = sum(n.get('memory_used', 0) for n in nodes)
    avg_cpu = sum(n.get('cpu_usage', 0) for n in nodes) / len(nodes) if nodes else 0
    
    # Get real system info
    system = get_system_info()
    
    return jsonify({
        'total_nodes': len(nodes),
        'running_nodes': running_nodes,
        'total_tasks': total_tasks,
        'completed_tasks': completed_tasks,
        'pending_tasks': pending_tasks,
        'total_memory_mb': total_memory,
        'used_memory_mb': used_memory,
        'avg_cpu_usage': round(avg_cpu, 1),
        'system': system
    })


if __name__ == '__main__':
    import os
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
