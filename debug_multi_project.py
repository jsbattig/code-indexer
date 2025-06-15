#!/usr/bin/env python3
import os
import sys
sys.path.insert(0, '/home/jsbattig/Dev/code-indexer/src')
from code_indexer.services.docker_manager import DockerManager

# Test status in different directories
print('=== Testing project name detection ===')
os.chdir('/home/jsbattig/Dev/code-indexer/tests/projects/test_project_1')
dm1 = DockerManager()
print('Project 1 name:', dm1.project_name)

os.chdir('/home/jsbattig/Dev/code-indexer/tests/projects/test_project_2')
dm2 = DockerManager()
print('Project 2 name:', dm2.project_name)

print('Different project names:', dm1.project_name != dm2.project_name)

# Test compose commands being generated
print('\n=== Testing compose commands ===')
print('Project 1 compose command:', dm1.get_compose_command())
print('Project 2 compose command:', dm2.get_compose_command())