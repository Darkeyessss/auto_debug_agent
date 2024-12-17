from clone_code import main as clone_main
from auto_install_with_gpt import main as install_main

def run_test():
    config_file = "config.json"

    print("开始克隆仓库...")
    clone_main()

    print("开始运行自动安装和实验...")
    install_main()

if __name__ == "__main__":
    run_test()
