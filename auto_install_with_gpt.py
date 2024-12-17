import os
import docker
import time
import openai
import platform
import subprocess
import json

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI


# 读取配置文件
def load_config(config_path='config.json'):
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"配置文件 {config_path} 未找到。")
    with open(config_path, 'r', encoding='utf-8') as f:
        return json.load(f)


config = load_config()

# 设置 API 密钥和 API 基础 URL
API_SECRET_KEY = config.get("api_secret_key")
BASE_URL = config.get("base_url")
os.environ["OPENAI_API_KEY"] = API_SECRET_KEY
os.environ["OPENAI_API_BASE"] = BASE_URL
openai.api_key = API_SECRET_KEY

# 创建 Docker 客户端
client = docker.from_env()


def get_system_info():
    """
    获取本机的硬件和软件配置信息，例如操作系统、Python 版本、GPU 信息等。
    """
    system = platform.system()
    python_version = platform.python_version()

    # 获取 GPU 信息（假设使用 NVIDIA GPU）
    try:
        gpu_info = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=name,driver_version,cuda_version", "--format=csv,noheader"],
            encoding='utf-8'
        ).strip()
    except Exception:
        gpu_info = "No GPU detected or nvidia-smi not available."

    return f"OS: {system}\nPython Version: {python_version}\nGPU Info: {gpu_info}"


def debug_installation(container, requirements_path, error_message, system_info):
    """
    使用 GPT-4 生成修复 pip 安装问题的命令。
    """
    try:
        messages = [
            SystemMessage(
                content=(
                    "You are a Python package installation expert. You will receive an error message from a pip install attempt, "
                    "and you need to provide a revised pip or apt or similar command that might fix the installation issue. "
                    "Consider the following system information to provide accurate commands. You MUST NOT output any analysis text. "
                    "ONLY output the revised command to run in the terminal, without ``` or code block notation."
                )
            ),
            HumanMessage(
                content=(
                    f'''We tried to run "pip install -r {requirements_path}" in a Docker container and got the following error message:
{error_message}

Here is the system information:
{system_info}

Please provide command lines that can fix the installation problem, it is fine to have multiple lines.
Remember: ONLY output the command itself, nothing else.
Don't include ```sh``` or ```bash``` in your answer, only the pure command which I can directly input to the terminal.'''
                )
            ),
        ]

        chat = ChatOpenAI(model="gpt-4", temperature=0)
        response = chat.batch([messages])[0].content.strip()
        return response
    except Exception as e:
        print(f"调用 GPT 获取安装命令时发生错误: {e}")
        return None


def install_requirements_with_enhancements(container, requirements_file, system_info, max_attempts=3):
    """
    安装 requirements.txt 中的依赖，并在遇到错误时使用 GPT-4 进行修复。
    """
    req_path = f"/mnt/code/{requirements_file}"
    attempt = 0
    while attempt < max_attempts:
        print(f"正在尝试安装 Python 依赖 (第 {attempt + 1} 次尝试)...")
        # 使用 /bin/bash -c 确保命令在支持 && 的 shell 中执行
        command = f"/bin/bash -c \"pip install --upgrade pip && pip install -r {req_path}\""
        install_result = container.exec_run(command, stderr=True, stdout=True)
        install_output = install_result.output.decode()
        print(install_output)

        # 检查安装是否成功
        if not any(err in install_output for err in ["ERROR:", "No matching distribution found", "failed"]):
            print("依赖安装成功！")
            return True

        # 如果出现错误，尝试让 GPT 生成修复命令
        print("依赖安装失败，使用 GPT 生成新的安装命令...")
        fix_command = debug_installation(container, req_path, install_output, system_info)
        if fix_command:
            print(f"尝试执行 GPT 提供的命令: {fix_command}")
            fix_result = container.exec_run(fix_command, stderr=True, stdout=True)
            fix_output = fix_result.output.decode()
            print(fix_output)
            # 再次检查是否安装成功
            if not any(err in fix_output for err in ["ERROR:", "No matching distribution found", "failed"]):
                print("通过 GPT 修改的命令安装成功！")
                return True
            else:
                print("通过 GPT 修改的命令仍然失败。")
        else:
            print("未能获得 GPT 的有效修正命令。")

        attempt += 1
        time.sleep(2)

    print("多次尝试后仍未能成功安装依赖。")
    return False


def get_successful_packages(install_output):
    """
    解析 pip 安装输出，获取成功安装的包列表，并包括其版本号。
    """
    success_packages = {}
    lines = install_output.split('\n')
    for line in lines:
        if "Successfully installed" in line:
            # 通过空格分割并去除多余的字符，解析出包和版本号
            parts = line.replace("Successfully installed", "").strip().split(' ')
            for part in parts:
                if '==' in part:  # 确保是带有版本号的包
                    pkg_name, pkg_version = part.split('==')
                    success_packages[pkg_name] = pkg_version
    return success_packages


def handle_specific_package_issues(container, requirements_file, successful_packages, system_info):
    """
    针对已安装成功的包和安装失败的包进行处理，例如删除并重装。
    """
    # 获取所有需要安装的包及其版本
    code_dir = "/mnt/code"  # 在容器内的代码目录
    req_path = f"{code_dir}/{requirements_file}"
    exec_result = container.exec_run(f"cat {req_path}", stderr=True, stdout=True)
    requirements_content = exec_result.output.decode()

    required_packages = {}
    for line in requirements_content.split('\n'):
        line = line.strip()
        if line:
            if '==' in line:
                pkg_name, pkg_version = line.split('==')  # 获取包名和版本
                required_packages[pkg_name] = pkg_version
            else:
                required_packages[line] = None  # 没有指定版本

    # 识别安装失败的包
    failed_packages = []
    for pkg_name, pkg_version in required_packages.items():
        # 检查当前包是否已经安装，并且版本是否匹配
        if pkg_name not in successful_packages:
            failed_packages.append(pkg_name)
        elif pkg_version and successful_packages.get(pkg_name) != pkg_version:
            failed_packages.append(pkg_name)

    if failed_packages:
        print(f"识别到安装失败的包: {failed_packages}")
        for pkg in failed_packages:
            print(f"尝试删除并重装包: {pkg}")
            # 删除包
            uninstall_result = container.exec_run(f"pip uninstall -y {pkg}", stderr=True, stdout=True)
            uninstall_output = uninstall_result.output.decode()
            print(uninstall_output)
            # 重新安装单个包
            install_single = container.exec_run(f"pip install {pkg}", stderr=True, stdout=True)
            install_single_output = install_single.output.decode()
            print(install_single_output)
            if any(err in install_single_output for err in ["ERROR:", "No matching distribution found", "failed"]):
                # 如果单个包安装失败，尝试使用 GPT 修复
                print(f"包 {pkg} 安装失败，使用 GPT 生成修复命令...")
                fix_command = debug_installation(container, req_path, install_single_output, system_info)
                if fix_command:
                    print(f"尝试执行 GPT 提供的命令: {fix_command}")
                    fix_result = container.exec_run(fix_command, stderr=True, stdout=True)
                    fix_output = fix_result.output.decode()
                    print(fix_output)
            else:
                print(f"包 {pkg} 安装成功！")
    else:
        print("所有包均已成功安装。")


def run_code_in_container(container, code_path, max_attempts=5):
    """
    在 Docker 容器中运行指定的 Python 脚本，并捕获其输出。
    """
    for attempt in range(max_attempts):
        print(f"尝试运行代码。第 {attempt + 1}/{max_attempts} 次尝试...")

        # 运行代码并捕获输出
        exec_result = container.exec_run(f"python /mnt/code/{os.path.basename(code_path)}", stderr=True, stdout=True)
        output = exec_result.output.decode()

        print("代码输出结果:")
        print(output)

        # 可以根据需要添加错误检测和修复逻辑
        # 这里暂时只运行一次，如果需要自动修复错误，可以启用相关代码

        # 示例：假设代码运行成功，直接返回输出
        if not any(err in output for err in ["SyntaxError", "Traceback", "ERROR"]):
            print("代码执行成功！")
            return output  # 返回成功的输出

        # 如果有错误，尝试修复代码
        print(f"检测到错误！使用 GPT 修复错误（第 {attempt + 1}/{max_attempts} 次尝试）...\n")
        success = modify_python_file(container, code_path, output)

        # 如果修复失败，继续尝试
        if not success:
            print("未能修改代码。正在重试...")
        else:
            print("重新尝试运行修改后的代码...")

        time.sleep(2)  # 等待一段时间后再尝试重新运行代码

    print("多次尝试后仍未能成功执行代码。")
    return None


def modify_python_file(container, file_path, error_message, max_retries=3, delay=5):
    """
    使用 GPT-4 修复代码中的错误，并将修复后的代码写回文件。
    """
    for attempt in range(max_retries):
        try:
            # 读取文件内容
            code = container.exec_run(f"cat /mnt/code/{os.path.basename(file_path)}").output.decode()

            messages = [
                SystemMessage(
                    content=(
                        "You are now a senior programmer proficient in Python code, capable of making responsive changes based on error messages."
                    )
                ),
                HumanMessage(content=(
                    f'''Here is my Python code:

{code}

And its error message is:

{error_message}

Please fix the bug based on the error message. Note that I need to use your response for direct execution. You MUST NOT output any analysis text. ONLY pure Python code output in the exact legal format is allowed. 
Don't include ```python``` in your answer, only the pure python code.'''
                )),
            ]

            chat = ChatOpenAI(model="gpt-4", temperature=0)
            response = chat.batch([messages])[0].content.strip()

            # 将生成的代码写回文件
            temp_code_path = "/mnt/code/temp_fixed_code.py"
            # 处理单引号以避免 shell 命令错误
            safe_response = response.replace("'", "'\"'\"'")
            container.exec_run(f"echo '{safe_response}' > {temp_code_path}")
            container.exec_run(f"mv {temp_code_path} /mnt/code/{os.path.basename(file_path)}")

            print(f"代码已被 GPT-4 修复（尝试 {attempt + 1}/{max_retries}）。")
            return True  # 成功修复，返回 True

        except Exception as e:
            print(f"尝试修复代码时发生错误（尝试 {attempt + 1}/{max_retries}）：{e}")
            time.sleep(delay)

    print("多次尝试后仍未能修复代码。")
    return False  # 尝试了 max_retries 次后仍然失败


def run_sandbox_experiment(
        repo_path,
        code_file_relative_path='test.py',
        requirements_file='requirements.txt',
        python_image="python:3.9-slim",
        max_install_attempts=3,
        max_run_attempts=5
):
    """
    运行沙盒实验的主函数。

    参数:
        repo_path (str): 克隆下来的仓库的本地路径。
        code_file_relative_path (str): 要运行的 Python 脚本相对于仓库根目录的路径。
        requirements_file (str): requirements.txt 文件名。
        python_image (str): 使用的 Python Docker 镜像。
        max_install_attempts (int): 安装依赖的最大尝试次数。
        max_run_attempts (int): 运行代码的最大尝试次数。

    返回:
        str: 代码运行的输出，如果运行失败则返回 None。
    """
    # 代码文件路径
    code_file_path = os.path.join(repo_path, code_file_relative_path)

    # 定义挂载点，将宿主机的代码目录挂载到容器
    code_dir = os.path.dirname(code_file_path)
    requirements_path = os.path.join(code_dir, requirements_file)

    if not os.path.exists(code_file_path):
        print(f"代码文件 {code_file_path} 不存在。")
        return None

    if not os.path.exists(requirements_path):
        print(f"requirements.txt 文件 {requirements_path} 不存在。")
        return None

    volume_binding = {
        code_dir: {'bind': '/mnt/code', 'mode': 'rw'},
    }

    # 启动 Docker 容器，使用特定的 Python 版本以确保兼容性
    container = client.containers.run(
        python_image,  # 使用指定的 Python 镜像
        "sleep 3600",  # 保持容器运行状态
        detach=True,
        volumes=volume_binding
    )
    print('容器 ID:', container.id)

    try:
        # 获取系统信息
        system_info = get_system_info()
        print("系统信息:")
        print(system_info)

        # 安装 Python 依赖（带有自动重试和 GPT 修正逻辑）
        if not install_requirements_with_enhancements(container, requirements_file, system_info,
                                                      max_attempts=max_install_attempts):
            print("无法完成依赖安装，程序终止。")
            return None

        print("依赖安装和处理完成。")

        # 运行代码并获取输出
        print("正在运行代码...")
        code_output = run_code_in_container(container, code_file_path, max_attempts=max_run_attempts)
        if code_output:
            print("代码成功运行，输出如下：")
            print("=" * 50)
            print(code_output)
            print("=" * 50)
            return code_output
        else:
            print("代码执行失败。")
            return None

    finally:
        # 停止并移除容器
        container.stop()
        container.remove()


def main():
    # 这里可以根据需要修改或传入参数
    repo_path = config.get("repo_path", 'D:/ada')  # 请替换为您的仓库路径
    code_file_relative_path = config.get("code_file_relative_path", 'test.py')
    requirements_file = config.get("requirements_file", 'requirements.txt')
    python_image = config.get("python_image", "python:3.9-slim")

    run_sandbox_experiment(
        repo_path=repo_path,
        code_file_relative_path=code_file_relative_path,
        requirements_file=requirements_file,
        python_image=python_image
    )


if __name__ == "__main__":
    main()
