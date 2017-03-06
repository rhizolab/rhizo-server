import os
import shutil
if not os.path.exists('settings'):
    print('creating settings folder')
    os.mkdir('settings')
if not os.path.exists('settings/__init__.py'):
    print('creating __init__.py')
    open('settings/__init__.py', 'w')
if not os.path.exists('settings/config.py'):
    print('copying settings file')
    shutil.copy('sample_settings/config.py', 'settings/config.py')
