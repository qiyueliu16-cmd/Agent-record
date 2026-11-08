PYTHON ?= python3

.PHONY: setup start headless check desktop stop demo

setup:
	$(PYTHON) scripts/install_skill.py

start:
	$(PYTHON) app/launcher.py

headless:
	$(PYTHON) app/launcher.py --no-window

check:
	$(PYTHON) app/launcher.py --selftest

desktop:
	$(PYTHON) app/build_desktop_app.py

stop:
	$(PYTHON) app/launcher.py --stop

demo:
	@echo "示例项目：examples/demo-project"
	@echo "账本：examples/demo-project/.agent-log/ledger.json"
	@echo "启动后在工作台点「生成报告」即可看到带图报告。"
