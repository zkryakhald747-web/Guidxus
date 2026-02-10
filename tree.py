import os

def print_tree(start_path, prefix=""):
    items = os.listdir(start_path)
    pointers = ["├── "] * (len(items) - 1) + ["└── "]
    for pointer, item in zip(pointers, items):
        path = os.path.join(start_path, item)
        print(prefix + pointer + item)
        if os.path.isdir(path):
            extension = "│   " if pointer == "├── " else "    "
            print_tree(path, prefix + extension)

base_path = r"C:\Users\hp\Desktop\project"
print_tree(base_path)