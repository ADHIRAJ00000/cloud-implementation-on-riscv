from datetime import datetime
from pymongo import MongoClient
from bson import ObjectId
from config import MONGODB_URI, DATABASE_NAME

client = MongoClient(MONGODB_URI)
db = client[DATABASE_NAME]

# Collections
nodes_collection = db['nodes']
tasks_collection = db['tasks']
logs_collection = db['logs']


class Node:
    @staticmethod
    def create(name, memory_mb=512, cpu_cores=1):
        node = {
            'name': name,
            'memory_mb': memory_mb,
            'cpu_cores': cpu_cores,
            'status': 'stopped',
            'memory_used': 0,
            'cpu_usage': 0,
            'created_at': datetime.utcnow(),
            'tasks_completed': 0
        }
        result = nodes_collection.insert_one(node)
        node['_id'] = result.inserted_id
        return node

    @staticmethod
    def get_all():
        return list(nodes_collection.find())

    @staticmethod
    def get_by_id(node_id):
        return nodes_collection.find_one({'_id': ObjectId(node_id)})

    @staticmethod
    def update_status(node_id, status):
        nodes_collection.update_one(
            {'_id': ObjectId(node_id)},
            {'$set': {'status': status}}
        )

    @staticmethod
    def update_usage(node_id, cpu_usage, memory_used):
        nodes_collection.update_one(
            {'_id': ObjectId(node_id)},
            {'$set': {'cpu_usage': cpu_usage, 'memory_used': memory_used}}
        )

    @staticmethod
    def increment_tasks(node_id):
        nodes_collection.update_one(
            {'_id': ObjectId(node_id)},
            {'$inc': {'tasks_completed': 1}}
        )

    @staticmethod
    def delete(node_id):
        nodes_collection.delete_one({'_id': ObjectId(node_id)})


class Task:
    @staticmethod
    def create(name, code, node_id=None):
        task = {
            'name': name,
            'code': code,
            'node_id': node_id,
            'status': 'pending',
            'output': '',
            'error': '',
            'created_at': datetime.utcnow(),
            'completed_at': None
        }
        result = tasks_collection.insert_one(task)
        task['_id'] = result.inserted_id
        return task

    @staticmethod
    def get_all():
        return list(tasks_collection.find().sort('created_at', -1))

    @staticmethod
    def get_pending():
        return list(tasks_collection.find({'status': 'pending'}))

    @staticmethod
    def update_status(task_id, status, output='', error=''):
        update = {'status': status}
        if output:
            update['output'] = output
        if error:
            update['error'] = error
        if status in ['completed', 'failed']:
            update['completed_at'] = datetime.utcnow()
        tasks_collection.update_one(
            {'_id': ObjectId(task_id)},
            {'$set': update}
        )

    @staticmethod
    def assign_node(task_id, node_id):
        tasks_collection.update_one(
            {'_id': ObjectId(task_id)},
            {'$set': {'node_id': node_id, 'status': 'running'}}
        )


class Log:
    @staticmethod
    def create(node_id, task_id, message, log_type='info'):
        log = {
            'node_id': node_id,
            'task_id': task_id,
            'message': message,
            'type': log_type,
            'timestamp': datetime.utcnow()
        }
        logs_collection.insert_one(log)

    @staticmethod
    def get_recent(limit=50):
        return list(logs_collection.find().sort('timestamp', -1).limit(limit))
