from setuptools import setup, find_packages

setup(
    name="crypto-trading-bot",
    version="1.0.0",
    description="AI Advanced Crypto Copy-Trading Bot",
    packages=find_packages(),
    python_requires=">=3.11",
    install_requires=[
        "ccxt>=4.0.0",
        "python-dotenv>=1.0.0",
        "pydantic>=2.0.0",
        "pydantic-settings>=2.0.0",
        "sqlalchemy>=2.0.0",
        "scikit-learn>=1.3.0",
        "pandas>=2.0.0",
        "numpy>=1.24.0",
        "ta>=0.11.0",
        "joblib>=1.3.0",
        "fastapi>=0.100.0",
        "uvicorn>=0.23.0",
        "jinja2>=3.1.0",
        "apscheduler>=3.10.0",
        "requests>=2.31.0",
        "cryptography>=41.0.0",
    ],
    entry_points={
        "console_scripts": [
            "trading-bot=bot.main:main",
        ],
    },
)
