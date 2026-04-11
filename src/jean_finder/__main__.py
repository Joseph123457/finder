import multiprocessing

from jean_finder.main import main

if __name__ == "__main__":
    # PyInstaller로 frozen된 exe에서 ProcessPoolExecutor가 자식 프로세스를
    # 무한 재실행하지 않도록 반드시 첫 줄에 가까운 위치에서 호출.
    multiprocessing.freeze_support()
    raise SystemExit(main())
