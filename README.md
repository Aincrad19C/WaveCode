# Wavemio

自研 CLI 编程智能体：手写 Agent 循环，不套 LangChain / AutoGen 等框架。吉祥物为社区二创 **鲸鱼娘** 的终端像素风立绘（参考 [Neko3000/deepseek-whalechan](https://github.com/Neko3000/deepseek-whalechan)，非官方）。

当前仓库：`--help` / `--version` 可用，工具循环尚未落地。设计见 `docs/`。CI/CD 见 `.github/workflows/`。

## 要求

- Python 3.11+
- 密钥只放环境变量或未入库的 `.env`，不要写进仓库

## 安装

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env   # 填入 DEEPSEEK_API_KEY，实现循环后再需要
```

```bash
wavemio --version
python -m coding_agent --version
```

## 测试

默认套件 **禁止真实网络**，与 GitHub Actions CI 相同：

```bash
ruff check src tests
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest
```

Agent 的 `wavemio run` / REPL 尚未实现，不要假定它们能干活。
