# auto_debug_agent

## Overview
This project automates the process of cloning a GitHub repository and executing a Python script within a sandbox environment. It retrieves the SSH URL of a specified repository using the GitHub GraphQL API and clones it into a designated local directory. After cloning, the script runs in an isolated environment (such as a virtual environment or Docker container) to ensure safe execution, preventing potential conflicts with your system environment.



## Features
 ### clone_code.py
- The script fetches the SSH clone URL for a given GitHub repository using the GraphQL API.
- It then clones the repository to a specified local path, ensuring the repository is downloaded only once (avoiding duplicates).
### auto_install_with_gpt.py
- After the repository is cloned, the script runs the test.py script in a controlled environment, isolating it from your main system.
- This prevents any possible interference with your local setup and ensures safe testing of the repository's functionality.
## Usage
1. Clone and Execute:

- Simply configure your GitHub credentials in the config.json file (which includes your GitHub token and GraphQL API URL).
- Run the script by executing python clone_and_run.py.
- The repository will be cloned, and the test.py script inside the repository will be executed within a sandbox environment.
2. Run Test:

- To test the repository's functionality, ensure that the test.py script is included in the repository you are cloning.
- Once the repository is cloned, the script will automatically execute the test.py file, allowing you to verify its behavior in isolation.


