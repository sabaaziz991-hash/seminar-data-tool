# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec — onedir build of the program (-> app\SeminarDataToolApp.exe), no console window.
# tkinter is included for the native Windows "Save as" / folder dialogs.
# Build:  python build.py   (runs PyInstaller with this spec, compiles the launcher, assembles and zips the package)

from PyInstaller.utils.hooks import collect_submodules

# numpy's C core imports these modules from C code, so the static analysis cannot see them
NUMPY_CORE = [m for m in collect_submodules("numpy._core") if "tests" not in m]

EXCLUDES = [
    # heavy packages that are installed on the build machine but not used by the tool
    "torch", "torchvision", "torchaudio", "tensorflow", "jax", "transformers", "open_clip", "pytorch_lightning",
    "torchmetrics", "lightning", "sklearn", "cv2", "numba", "llvmlite",
    "matplotlib", "PIL", "IPython", "jupyter_client", "jupyter_core", "notebook", "ipykernel",
    "pytest", "_pytest", "sphinx", "docutils", "playwright", "win32com", "pythoncom", "pywintypes", "comtypes",
    "huggingface_hub", "datasets", "fsspec", "sqlalchemy", "lxml", "jinja2", "bokeh", "plotly", "dask", "xarray",
    "tables", "h5py", "numexpr", "bottleneck", "pdfminer", "docx", "requests", "urllib3", "certifi",
    "setuptools", "pkg_resources",
    # test suites shipped inside libraries
    "pandas.tests", "numpy.tests", "scipy.tests", "statsmodels.tests", "pyarrow.tests",
]

a = Analysis(
    ["SeminarDataTool.py"],
    pathex=["."],
    binaries=[],
    datas=[("seminar_tool/web", "web")],
    hiddenimports=[
        "statsmodels.stats.contingency_tables", "statsmodels.stats.power", "statsmodels.stats.proportion",
        "pyarrow.parquet", "openpyxl", "openpyxl.cell._writer",
        "scipy._cyutility",           # shared Cython utility module of scipy >= 1.16 (imported from C)
        "tkinter", "tkinter.filedialog",
    ] + NUMPY_CORE,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=EXCLUDES,
    noarchive=False,
    optimize=0,
)

# drop Arrow components the tool never loads (Flight RPC, Substrait, Gandiva) to keep the ZIP small
DROP = ("arrow_flight", "_flight", "arrow_substrait", "_substrait", "gandiva", "_gandiva")
a.binaries = [b for b in a.binaries if not any(x in b[0].replace("\\", "/").split("/")[-1] for x in DROP)]


def _keep(dest):
    d = dest.replace("\\", "/")
    # test suites and the C/C++ headers of Arrow are not needed at run time (smaller ZIP, shorter paths)
    return "/tests/" not in d and not d.startswith(("pyarrow/include/", "pyarrow/src/"))


a.datas = [d for d in a.datas if _keep(d[0])]

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="SeminarDataToolApp",
    icon="app.ico",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="SeminarDataToolApp",
)
