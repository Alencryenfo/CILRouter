# 📁 CIL Router 项目结构

## 🏗️ 项目目录结构

```
CILRouter/
├── 📄 核心文档
│   ├── README.md                    # 项目主要说明文档
│   ├── README_EN.md                 # 英文说明文档  
│   ├── CLAUDE.md                    # Claude Code 项目配置
│   ├── LICENSE                      # 开源许可证
│   └── PROJECT_STRUCTURE.md         # 项目结构说明（本文件）
│
├── 🚀 应用程序
│   └── app/
│       ├── __init__.py
│       ├── main.py                  # 主应用入口
│       ├── middleware/              # 中间件
│       │   ├── __init__.py
│       │   └── rate_limiter.py      # 限流中间件
│       ├── utils/                   # 工具模块
│       │   ├── __init__.py
│       │   └── logger.py            # 日志工具
│       └── data/                    # 应用数据
│           ├── blocked_ips.json     # 阻止IP列表
│           └── log/                 # 日志目录
│               └── cilrouter.log    # 应用日志
│
├── ⚙️ 配置模块
│   └── config/
│       ├── __init__.py
│       └── config.py                # 配置管理
│
├── 🧪 测试套件
│   └── test_suites/
│       ├── __init__.py
│       ├── unit/                    # 单元测试
│       │   ├── __init__.py
│       │   ├── conftest.py          # pytest 配置
│       │   ├── test_main.py         # 基础功能测试
│       │   ├── test_comprehensive_functionality.py  # 全面功能测试
│       │   ├── test_streaming_functionality.py      # 流式处理测试
│       │   ├── test_rate_limit_comprehensive.py     # 限流功能测试
│       │   ├── test_streaming_error_direct.py       # 流式错误测试
│       │   ├── test_streaming_error_fix_validation.py # 修复验证测试
│       │   └── test_streaming_error_issue.py        # 错误问题测试
│       ├── integration/             # 集成测试
│       │   ├── __init__.py
│       │   ├── test_final_integration.py      # 最终集成测试
│       │   ├── test_integration_final.py      # 集成测试（备用）
│       │   └── test_error_handling_failover.py # 错误处理集成测试
│       ├── stress/                  # 压力测试
│       │   ├── __init__.py
│       │   ├── test_extreme_stress.py         # 极端压力测试
│       │   ├── test_rate_limit_extreme.py     # 限流极限测试
│       │   └── test_advanced_robustness.py    # 高级健壮性测试
│       ├── security/               # 安全测试
│       │   ├── __init__.py
│       │   └── test_logger_robustness.py      # 日志安全测试
│       ├── performance/            # 性能测试
│       │   └── __init__.py
│       └── reports/                # 测试报告
│           ├── __init__.py
│           └── comprehensive_test_report.py   # 综合测试报告生成器
│
├── 📚 文档目录
│   └── docs/
│       ├── reports/                 # 测试报告
│       │   ├── comprehensive_test_report.md     # 综合测试报告
│       │   ├── final_test_summary.md           # 最终测试总结
│       │   └── streaming_error_fix_report.md   # 流式错误修复报告
│       ├── api/                     # API 文档（预留）
│       └── deployment/              # 部署文档（预留）
│
├── 🐳 部署配置
│   ├── Dockerfile                   # Docker 镜像构建
│   ├── docker-compose.yml          # Docker Compose 配置
│   └── requirements.txt             # Python 依赖
│
└── 📋 其他文件
    └── cilrouter.log               # 根目录日志文件
```

## 📂 目录详细说明

### 🚀 应用程序 (`app/`)
包含CIL Router的核心应用代码：

- **`main.py`**: 主应用文件，包含FastAPI应用和路由处理
- **`middleware/`**: 中间件模块
  - `rate_limiter.py`: 基于令牌桶算法的限流中间件
- **`utils/`**: 通用工具模块
  - `logger.py`: 结构化日志记录工具
- **`data/`**: 应用运行时数据
  - `blocked_ips.json`: IP阻止列表
  - `log/`: 日志文件存储目录

### ⚙️ 配置模块 (`config/`)
- **`config.py`**: 统一配置管理，支持环境变量和默认配置

### 🧪 测试套件 (`test_suites/`)
按功能和类型分类的测试代码：

#### 单元测试 (`unit/`)
- 基础功能测试
- 组件级测试
- API端点测试
- 流式处理测试
- 限流功能测试

#### 集成测试 (`integration/`)
- 端到端测试
- 多模块协作测试
- 环境配置测试
- 错误处理集成测试

#### 压力测试 (`stress/`)
- 高并发测试
- 资源耗尽测试
- 极端条件测试
- 性能基准测试

#### 安全测试 (`security/`)
- 安全漏洞测试
- 攻击防护测试
- 输入验证测试
- 权限控制测试

#### 性能测试 (`performance/`)
- 响应时间测试
- 吞吐量测试
- 资源使用测试
- 扩展性测试

#### 测试报告 (`reports/`)
- 自动化测试报告生成器
- 测试结果汇总工具

### 📚 文档目录 (`docs/`)
项目相关文档：

- **`reports/`**: 测试报告和分析文档
- **`api/`**: API文档（预留，可添加OpenAPI规范等）
- **`deployment/`**: 部署指南和运维文档（预留）

## 🎯 目录设计原则

### 1. **分离关注点**
- 应用代码、配置、测试、文档完全分离
- 测试按类型和功能进一步分类

### 2. **可扩展性**
- 预留了API文档、部署文档等目录
- 性能测试目录为未来扩展做准备

### 3. **开发友好**
- 清晰的目录结构便于新开发者理解
- 测试文件按功能分类，易于维护

### 4. **CI/CD友好**
- 测试按类型分组，可以分阶段运行
- 报告生成器可以集成到自动化流程

## 🔧 使用指南

### 运行不同类型的测试

```bash
# 运行单元测试
python -m pytest test_suites/unit/ -v

# 运行集成测试
python -m pytest test_suites/integration/ -v

# 运行压力测试
python -m pytest test_suites/stress/ -v

# 运行安全测试
python -m pytest test_suites/security/ -v

# 运行所有测试
python -m pytest test_suites/ -v

# 生成综合测试报告
python test_suites/reports/comprehensive_test_report.py
```

### 添加新测试

1. **单元测试**: 添加到 `test_suites/unit/`
2. **集成测试**: 添加到 `test_suites/integration/`
3. **性能测试**: 添加到 `test_suites/performance/`
4. **安全测试**: 添加到 `test_suites/security/`

### 文档管理

1. **测试报告**: 保存到 `docs/reports/`
2. **API文档**: 保存到 `docs/api/`
3. **部署文档**: 保存到 `docs/deployment/`

## 📋 文件命名规范

- **测试文件**: `test_*.py`
- **配置文件**: `*_config.py` 或 `config.py`
- **工具文件**: `*_utils.py` 或放在 `utils/` 目录
- **文档文件**: `*.md`
- **报告文件**: `*_report.*`

---

**维护者**: CIL Router 开发团队  
**最后更新**: 2025年8月12日  
**版本**: 1.0.1