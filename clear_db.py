"""
Script to clear all data from the cloud_riscv database.
Run this before a demo to start fresh.
"""

from config import MONGODB_URI, DATABASE_NAME
from pymongo import MongoClient

def clear_database():
    client = MongoClient(MONGODB_URI)
    db = client[DATABASE_NAME]
    
    # Clear all collections
    nodes = db['nodes'].delete_many({})
    tasks = db['tasks'].delete_many({})
    logs = db['logs'].delete_many({})
    
    print(f"Cleared database: {DATABASE_NAME}")
    print(f"  - Nodes deleted: {nodes.deleted_count}")
    print(f"  - Tasks deleted: {tasks.deleted_count}")
    print(f"  - Logs deleted: {logs.deleted_count}")
    print("\nDatabase is now empty. Ready for demo!")

if __name__ == '__main__':
    confirm = input("This will delete ALL data. Are you sure? (yes/no): ")
    if confirm.lower() == 'yes':
        clear_database()
    else:
        print("Cancelled.")
