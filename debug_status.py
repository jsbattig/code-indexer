#!/usr/bin/env python3
import os
import sys
import time
sys.path.insert(0, '/home/jsbattig/Dev/code-indexer/src')
from code_indexer.services.docker_manager import DockerManager

# Set up both projects similar to the test
print('=== Setting up project managers ===')
os.chdir('/home/jsbattig/Dev/code-indexer/tests/projects/test_project_1')
dm1 = DockerManager()
print(f'Project 1 name: {dm1.project_name}')

os.chdir('/home/jsbattig/Dev/code-indexer/tests/projects/test_project_2')
dm2 = DockerManager()
print(f'Project 2 name: {dm2.project_name}')

print('\n=== Starting containers ===')
print('Starting project 1...')
result1 = dm1.start()
print(f'Project 1 start result: {result1}')

print('Starting project 2...')
result2 = dm2.start()
print(f'Project 2 start result: {result2}')

print('\n=== Waiting for containers to be ready ===')
time.sleep(5)

print('\n=== Checking status ===')
status1 = dm1.status()
status2 = dm2.status()

print(f'Status 1: {status1}')
print(f'Status 2: {status2}')

print('\n=== Stopping containers ===')
dm1.stop()
dm2.stop()