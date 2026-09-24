import os
import kagglehub


def main() -> None:
    path = kagglehub.dataset_download("abbas829/global-superstore-sales-dataset")

    print("Dataset downloaded to:", path)

    for file in os.listdir(path):
        print(file)
