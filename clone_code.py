import os
import requests
import subprocess
import json


# 读取配置文件
def load_config():
    with open('config.json', 'r') as f:
        config = json.load(f)
    return config


# 获取 GitHub 仓库的克隆 URL
def get_clone_url(owner, repo, config):
    graphql_url = config["GITHUB_GRAPHQL_URL"]
    token = config["GITHUB_TOKEN"]

    # GraphQL 查询，用于获取仓库的克隆 URL
    query = """
    {
      repository(owner: "%s", name: "%s") {
        sshUrl
      }
    }
    """ % (owner, repo)

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    # 发送请求
    response = requests.post(graphql_url, json={'query': query}, headers=headers)

    if response.status_code == 200:
        data = response.json()
        try:
            clone_url = data['data']['repository']['sshUrl']
            return clone_url
        except KeyError:
            print(f"Error: Repository not found or no SSH URL available.")
            return None
    else:
        print(f"Error: {response.status_code} - {response.text}")
        return None


# 克隆 GitHub 仓库
def clone_repository(owner, repo, clone_url, destination):
    # 创建目标路径下与仓库同名的目录
    repo_name = repo
    target_path = os.path.join(destination, repo_name)

    # 如果目录已存在，提示并避免重复克隆
    if os.path.exists(target_path):
        print(f"Directory '{target_path}' already exists. Skipping clone.")
        return

    try:
        print(f"Cloning repository from {clone_url} to {target_path}...")
        subprocess.check_call(['git', 'clone', clone_url, target_path])
        print("Repository cloned successfully.")
    except subprocess.CalledProcessError as e:
        print(f"Error while cloning repository: {e}")

def main():
    # 从配置文件中加载配置信息
    config = load_config()

    # 仓库信息
    owner = "Darkeyessss"
    repo = "test"
    destination = "C:\\Users\\18176\\Desktop\\auto_debug_agent"

    # 获取克隆 URL
    clone_url = get_clone_url(owner, repo, config)

    # 克隆仓库到指定路径
    clone_repository(owner, repo, clone_url, destination)


if __name__ == '__main__':
    main()
