# Blockchain Lab — Proof of Existence (Sepolia Enhanced)

> 🎓 **学习型项目** — 区块链存证原型系统，用于学习 Solidity + Python + Web3 开发。
>
> ⚠️ 这不是正式的版权存证产品，仅作为技术学习和教学案例使用。

## 📋 项目简介

本项目实现了一个基于以太坊 Sepolia 测试网的 **Proof of Existence (存在性证明)** 系统：

1. 计算文件的 SHA-256 哈希
2. 将哈希提交到智能合约
3. 利用区块链的不可篡改性证明文件在特定时间点的存在

### 技术栈

| 层级 | 技术 | 用途 |
|------|------|------|
| 智能合约 | Solidity 0.8.24 / Foundry | ProofOfExistence 合约 |
| 客户端 | Python 3.12+ / web3.py | 文件注册、验证、证据管理 |
| 底层概念 | C++ | 区块链基础数据结构学习 |
| 测试网 | Ethereum Sepolia | 链上部署与交互 |

## 🏗️ 项目结构

```
blockchain-lab-Sepolia-POE-Enhance/
│
├── contracts/                  # Solidity 智能合约 (Foundry)
│   ├── src/ProofOfExistence.sol
│   ├── test/
│   ├── foundry.toml
│   └── .env.example
│
├── python-client/              # Python 客户端工具包
│   ├── proof_client/           # 核心包
│   │   ├── config.py           #   统一配置管理
│   │   ├── hash_file.py        #   SHA-256 哈希计算
│   │   ├── wallet.py           #   Web3 连接 & 钱包管理
│   │   ├── contract_client.py  #   合约调用封装
│   │   ├── evidence_schema.py  #   证据数据结构 (dataclass)
│   │   ├── evidence_store.py   #   证据 JSON 持久化
│   │   ├── evidence_repository.py  # 证据 SQLite 持久化
│   │   ├── register_file.py    #   注册文件到链上
│   │   ├── verify_file.py      #   验证文件链上状态
│   │   ├── batch_register.py   #   批量注册
│   │   ├── generate_report.py  #   Markdown 存证报告
│   │   ├── query_evidence.py   #   查询证据记录
│   │   └── test_all.py         #   全模块测试
│   ├── abi/ProofOfExistence.json
│   ├── works/                  #   待注册的作品文件
│   ├── evidence/               #   生成的证据 JSON
│   ├── reports/                #   生成的存证报告
│   ├── .env.example
│   └── requirements.txt
│
├── cpp-core/                   # C++ 区块链概念学习
│
├── docs/                       # 设计文档
│   ├── proof_of_existence_design.md
│   ├── evidence_package.md
│   └── ...
│
└── README.md
```

## 🚀 快速开始

### 前置要求

- Python 3.12+
- [Foundry](https://getfoundry.sh/) (用于合约编译和部署)
- Sepolia 测试网 ETH (可从 [faucet](https://www.alchemy.com/faucets/ethereum-sepolia) 获取)
- Alchemy / Infura RPC API Key

### 1. 克隆项目

```bash
git clone https://github.com/your-username/blockchain-lab-Sepolia-POE-Enhance.git
cd blockchain-lab-Sepolia-POE-Enhance
```

### 2. 配置环境

```bash
# Python 客户端
cd python-client
cp .env.example .env
# 编辑 .env，填入你的 RPC_URL、PRIVATE_KEY、CONTRACT_ADDRESS
nano .env

# 创建虚拟环境并安装依赖
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. 使用

```bash
cd python-client
export PYTHONPATH=.

# 计算文件哈希
python -m proof_client.hash_file works/sample_work.txt

# 注册文件到链上
python -m proof_client.register_file works/sample_work.txt

# 验证文件
python -m proof_client.verify_file works/sample_work.txt

# 批量注册 works/ 目录下的所有文件
python -m proof_client.batch_register

# 生成存证报告
python -m proof_client.generate_report <file_hash>
python -m proof_client.generate_report --all

# 查询证据
python -m proof_client.query_evidence --all
python -m proof_client.query_evidence --hash <file_hash>
python -m proof_client.query_evidence --owner <address>
python -m proof_client.query_evidence --stats
```

### 4. 运行测试

```bash
cd python-client
export PYTHONPATH=.

# 本地测试（不连链，49 项测试）
python -m proof_client.test_all

# 含链上测试（需要 Sepolia ETH，会消耗 gas）
python -m proof_client.test_all --chain
```

## 📝 智能合约

[ProofOfExistence.sol](contracts/src/ProofOfExistence.sol) 提供两个核心方法：

| 方法 | 类型 | 说明 |
|------|------|------|
| `register(bytes32 fileHash, string uri)` | 写入 | 将文件哈希注册到链上 |
| `verify(bytes32 fileHash)` | 只读 | 查询文件的注册信息 |

### 合约部署 (Foundry)

```bash
cd contracts
cp .env.example .env
# 编辑 .env

source .env
forge script --broadcast --rpc-url $SEPOLIA_RPC_URL \
  --private-key $SEPOLIA_PRIVATE_KEY \
  script/Deploy.s.sol
```

## 🔒 安全注意事项

> **⚠️ 重要：** 本项目中的 `.env` 文件包含敏感信息，已被 `.gitignore` 忽略。

- **绝不提交** 真实私钥 (`PRIVATE_KEY`) 到 Git
- **绝不提交** 包含 API Key 的 RPC URL
- 使用 `.env.example` 作为模板，在本地创建 `.env`
- 建议使用专用的测试钱包，与主钱包隔离

## 📚 适用场景

- 🎓 区块链技术学习
- 📖 Solidity + Python 工程案例
- 🔐 Proof of Existence 存证原型
- 👨‍🏫 教学演示
- 📝 技术博客配套代码

## 📄 License

MIT License — 仅供学习使用。
