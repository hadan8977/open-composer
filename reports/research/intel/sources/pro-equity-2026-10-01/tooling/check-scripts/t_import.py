import importlib,sys
for m in ["numpy","pandas","scipy","sklearn","cvxpy","clarabel","osqp","scs","highspy","skfolio","cvxportfolio","alphalens","pyfolio","empyrical","statsmodels","riskfolio","quantstats","purgedcv","vectorbt","numba"]:
    try:
        mod=importlib.import_module(m); print(m,"OK",getattr(mod,"__version__","?"))
    except Exception as e: print(m,"FAIL",type(e).__name__,str(e)[:150])
import cvxpy; print(cvxpy.installed_solvers())
