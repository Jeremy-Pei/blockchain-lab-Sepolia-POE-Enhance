"""
test_all.py — 全模块测试脚本

测试策略：
  ┌─────────────────────────────────────────────────────────────────┐
  │ 第 1 层：纯本地模块（无需网络 / 合约交互）                        │
  │   config, hash_file, evidence_schema,                          │
  │   evidence_store, evidence_repository                          │
  │                                                                │
  │ 第 2 层：需要钱包但不需要链上交互                                 │
  │   wallet (仅测试本地密钥 → 地址推导)                              │
  │                                                                │
  │ 第 3 层：需要链上交互（RPC 连接 + 合约调用）                      │
  │   contract_client, register_file, verify_file, batch_register  │
  │                                                                │
  │ 第 4 层：依赖已有证据数据                                        │
  │   generate_report, query_evidence                              │
  └─────────────────────────────────────────────────────────────────┘

用法:
  cd python-client
  PYTHONPATH=. .venv/bin/python -m proof_client.test_all          # 仅本地测试
  PYTHONPATH=. .venv/bin/python -m proof_client.test_all --chain  # 含链上测试
"""

import sys
import os
import tempfile
import json
from pathlib import Path

# ══════════════════════════════════════════════════════════════════
# 测试工具
# ══════════════════════════════════════════════════════════════════

_passed = 0
_failed = 0


def ok(name: str, detail: str = ""):
    global _passed
    _passed += 1
    suffix = f" → {detail}" if detail else ""
    print(f"  ✅ {name}{suffix}")


def fail(name: str, err: str):
    global _failed
    _failed += 1
    print(f"  ❌ {name} → {err}")


def section(title: str):
    print(f"\n{'━'*60}")
    print(f"  📦 {title}")
    print(f"{'━'*60}")


# ══════════════════════════════════════════════════════════════════
# 第 1 层：纯本地模块
# ══════════════════════════════════════════════════════════════════

def test_config():
    """测试 config.py — 配置加载与路径常量。"""
    section("config.py")
    try:
        from proof_client.config import (
            PROJECT_ROOT, ABI_DIR, WORKS_DIR, EVIDENCE_DIR,
            REPORTS_DIR, DB_PATH, RPC_URL, PRIVATE_KEY,
            CONTRACT_ADDRESS, CHAIN_ID, EXPLORER_TX_URL, load_abi,
        )

        # 路径存在性
        assert PROJECT_ROOT.exists(), "PROJECT_ROOT 不存在"
        ok("PROJECT_ROOT 存在", str(PROJECT_ROOT))

        assert ABI_DIR.exists(), "ABI_DIR 不存在"
        ok("ABI_DIR 存在")

        for name, d in [("WORKS_DIR", WORKS_DIR), ("EVIDENCE_DIR", EVIDENCE_DIR), ("REPORTS_DIR", REPORTS_DIR)]:
            assert d.exists(), f"{name} 不存在"
        ok("WORKS_DIR / EVIDENCE_DIR / REPORTS_DIR 均存在")

        # 环境变量
        assert RPC_URL != "", "RPC_URL 为空"
        ok("RPC_URL 已加载", RPC_URL[:40] + "...")

        assert PRIVATE_KEY != "", "PRIVATE_KEY 为空"
        ok("PRIVATE_KEY 已加载", f"长度={len(PRIVATE_KEY)}")

        assert CONTRACT_ADDRESS != "", "CONTRACT_ADDRESS 为空"
        ok("CONTRACT_ADDRESS 已加载", CONTRACT_ADDRESS)

        assert CHAIN_ID == 11155111, f"CHAIN_ID 应为 11155111, 实际={CHAIN_ID}"
        ok("CHAIN_ID 正确", str(CHAIN_ID))

        assert "etherscan" in EXPLORER_TX_URL, "EXPLORER_TX_URL 格式异常"
        ok("EXPLORER_TX_URL 正确", EXPLORER_TX_URL)

        # ABI 加载
        abi = load_abi()
        assert isinstance(abi, list), "ABI 应为 list"
        assert len(abi) == 3, f"ABI 应有 3 项 (register, verify, Registered), 实际={len(abi)}"
        func_names = {item.get("name") for item in abi}
        assert "register" in func_names, "ABI 缺少 register"
        assert "verify" in func_names, "ABI 缺少 verify"
        ok("load_abi() 正确", f"{len(abi)} 项: {func_names}")

    except Exception as e:
        fail("config", str(e))


def test_hash_file():
    """测试 hash_file.py — SHA-256 哈希计算。"""
    section("hash_file.py")
    try:
        from proof_client.hash_file import sha256_hash

        # 1) 对已知文件计算哈希
        works_file = Path("works/my_first_work.txt")
        if works_file.exists():
            h = sha256_hash(str(works_file))
            assert h.startswith("0x"), "哈希应以 0x 开头"
            assert len(h) == 66, f"哈希长度应为 66 (0x + 64), 实际={len(h)}"
            ok("已知文件哈希", h[:20] + "...")
        else:
            fail("已知文件", "works/my_first_work.txt 不存在")

        # 2) 对临时文件计算哈希 → 验证确定性
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("hello blockchain")
            tmp_path = f.name

        h1 = sha256_hash(tmp_path)
        h2 = sha256_hash(tmp_path)
        assert h1 == h2, "同一文件两次哈希应一致"
        ok("确定性验证", "同文件两次哈希一致")
        os.unlink(tmp_path)

        # 3) 不同内容 → 不同哈希
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("content A")
            tmp_a = f.name
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("content B")
            tmp_b = f.name

        ha = sha256_hash(tmp_a)
        hb = sha256_hash(tmp_b)
        assert ha != hb, "不同内容的哈希应不同"
        ok("差异性验证", "不同内容 → 不同哈希")
        os.unlink(tmp_a)
        os.unlink(tmp_b)

        # 4) 文件不存在 → 抛异常
        try:
            sha256_hash("/nonexistent/file.txt")
            fail("异常处理", "应抛出 FileNotFoundError")
        except FileNotFoundError:
            ok("FileNotFoundError", "文件不存在时正确抛出异常")

    except Exception as e:
        fail("hash_file", str(e))


def test_evidence_schema():
    """测试 evidence_schema.py — 数据结构与序列化。"""
    section("evidence_schema.py")
    try:
        from proof_client.evidence_schema import EvidenceRecord

        # 1) 创建实例
        r = EvidenceRecord(
            file_name="test.txt",
            file_hash="0xabcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890",
            uri="sepolia://test.txt",
            tx_hash="aabbccdd",
            block_number=12345,
            gas_used=50000,
            owner="0x1234567890abcdef1234567890abcdef12345678",
            timestamp=1718000000,
            status="success",
            contract_address="0xContractAddress",
            explorer_tx_url="https://sepolia.etherscan.io/tx/",
        )
        ok("创建实例", f"file_name={r.file_name}")

        # 2) to_dict
        d = r.to_dict()
        assert isinstance(d, dict), "to_dict 应返回 dict"
        assert d["file_name"] == "test.txt"
        assert d["block_number"] == 12345
        ok("to_dict", f"{len(d)} 个字段")

        # 3) from_dict (正常)
        r2 = EvidenceRecord.from_dict(d)
        assert r2.file_name == r.file_name
        assert r2.block_number == r.block_number
        ok("from_dict 正常", f"file={r2.file_name}, block={r2.block_number}")

        # 4) from_dict (含多余字段 → 应忽略)
        d_extra = {**d, "unknown_field": "should_be_ignored", "id": 999}
        r3 = EvidenceRecord.from_dict(d_extra)
        assert r3.file_name == "test.txt"
        ok("from_dict 过滤无效键", "多余字段被安全忽略")

        # 5) timestamp_utc 属性
        assert r.timestamp_utc != "N/A", "有时间戳时不应为 N/A"
        assert "UTC" in r.timestamp_utc
        ok("timestamp_utc", r.timestamp_utc)

        # 6) timestamp_utc 为 0 时
        r_zero = EvidenceRecord(file_name="x", file_hash="0x00", uri="x", timestamp=0)
        assert r_zero.timestamp_utc == "N/A"
        ok("timestamp_utc (零值)", "返回 N/A")

        # 7) explorer_link 属性
        assert r.explorer_link.startswith("https://")
        assert "aabbccdd" in r.explorer_link
        ok("explorer_link", r.explorer_link)

        # 8) explorer_link 为空时
        r_empty = EvidenceRecord(file_name="x", file_hash="0x00", uri="x")
        assert r_empty.explorer_link == ""
        ok("explorer_link (空值)", "返回空字符串")

    except Exception as e:
        fail("evidence_schema", str(e))


def test_evidence_store():
    """测试 evidence_store.py — JSON 文件持久化。"""
    section("evidence_store.py")
    try:
        from proof_client.evidence_schema import EvidenceRecord
        from proof_client.evidence_store import save_evidence, load_evidence, list_all_evidence
        from proof_client.config import EVIDENCE_DIR

        test_hash = "0x_test_store_1234567890abcdef1234567890abcdef1234567890abcdef12345678"

        r = EvidenceRecord(
            file_name="store_test.txt",
            file_hash=test_hash,
            uri="sepolia://store_test.txt",
            status="success",
        )

        # 1) 保存
        path = save_evidence(r)
        assert path.exists(), "保存后文件应存在"
        ok("save_evidence", str(path.name))

        # 2) 加载
        loaded = load_evidence(test_hash)
        assert loaded is not None, "应能加载刚保存的证据"
        assert loaded.file_name == "store_test.txt"
        assert loaded.file_hash == test_hash
        ok("load_evidence", f"file={loaded.file_name}")

        # 3) 加载不存在的哈希
        missing = load_evidence("0xnon_existent_hash_0000000000000000000000000000000000000000")
        assert missing is None, "不存在的哈希应返回 None"
        ok("load_evidence (不存在)", "返回 None")

        # 4) list_all_evidence
        all_records = list_all_evidence()
        assert any(r.file_hash == test_hash for r in all_records)
        ok("list_all_evidence", f"共 {len(all_records)} 条")

        # 5) JSON 内容验证
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert data["file_name"] == "store_test.txt"
        assert data["status"] == "success"
        ok("JSON 内容正确", "字段值匹配")

        # 清理
        path.unlink()
        ok("清理测试文件")

    except Exception as e:
        fail("evidence_store", str(e))


def test_evidence_repository():
    """测试 evidence_repository.py — SQLite 持久化。"""
    section("evidence_repository.py")
    try:
        from proof_client.evidence_schema import EvidenceRecord
        from proof_client import evidence_repository as repo
        from proof_client.config import DB_PATH

        test_hash = "0x_test_repo_unique_hash_" + "a" * 40

        r = EvidenceRecord(
            file_name="repo_test.txt",
            file_hash=test_hash,
            uri="sepolia://repo_test.txt",
            owner="0xTestOwnerAddress",
            status="success",
        )

        # 1) count (初始)
        count_before = repo.count()
        ok("count()", f"当前记录数={count_before}")

        # 2) insert
        rowid = repo.insert(r)
        assert rowid > 0, "insert 应返回正整数 rowid"
        ok("insert", f"rowid={rowid}")

        # 3) count (插入后)
        count_after = repo.count()
        assert count_after == count_before + 1
        ok("count() 增加", f"{count_before} → {count_after}")

        # 4) find_by_hash
        found = repo.find_by_hash(test_hash)
        assert found is not None
        assert found.file_name == "repo_test.txt"
        ok("find_by_hash", f"file={found.file_name}")

        # 5) find_by_hash (不存在)
        not_found = repo.find_by_hash("0xnon_existent_" + "b" * 50)
        assert not_found is None
        ok("find_by_hash (不存在)", "返回 None")

        # 6) find_by_owner
        by_owner = repo.find_by_owner("0xTestOwnerAddress")
        assert len(by_owner) >= 1
        assert any(r.file_hash == test_hash for r in by_owner)
        ok("find_by_owner", f"找到 {len(by_owner)} 条")

        # 7) find_all
        all_records = repo.find_all()
        assert len(all_records) >= 1
        ok("find_all", f"共 {len(all_records)} 条")

        # 8) 重复插入 → 应报错 (UNIQUE 约束)
        try:
            repo.insert(r)
            fail("UNIQUE 约束", "重复插入应报错")
        except Exception:
            ok("UNIQUE 约束", "重复哈希插入被正确拒绝")

        # 清理：删除测试数据库
        if DB_PATH.exists():
            DB_PATH.unlink()
            ok("清理测试数据库")

    except Exception as e:
        fail("evidence_repository", str(e))


# ══════════════════════════════════════════════════════════════════
# 第 2 层：钱包（本地密钥推导，不需要网络）
# ══════════════════════════════════════════════════════════════════

def test_wallet():
    """测试 wallet.py — 本地密钥推导。"""
    section("wallet.py")
    try:
        from proof_client.wallet import get_account, get_address, get_chain_id

        # 1) get_account
        account = get_account()
        assert account is not None
        assert hasattr(account, "address")
        ok("get_account", f"type={type(account).__name__}")

        # 2) get_address
        addr = get_address()
        assert addr.startswith("0x"), "地址应以 0x 开头"
        assert len(addr) == 42, f"地址长度应为 42, 实际={len(addr)}"
        ok("get_address", addr)

        # 3) get_chain_id
        chain_id = get_chain_id()
        assert chain_id == 11155111
        ok("get_chain_id", str(chain_id))

        # 4) 地址一致性
        assert account.address == addr
        ok("地址一致性", "account.address == get_address()")

    except Exception as e:
        fail("wallet", str(e))


# ══════════════════════════════════════════════════════════════════
# 第 3 层：链上交互（需要 --chain 参数）
# ══════════════════════════════════════════════════════════════════

def test_contract_client():
    """测试 contract_client.py — 合约连接与 verify。"""
    section("contract_client.py (链上)")
    try:
        from proof_client.contract_client import verify_hash

        # verify 一个不存在的哈希 → 应返回 timestamp=0
        fake_hash = "0x0000000000000000000000000000000000000000000000000000000000000001"
        result = verify_hash(fake_hash)
        assert "registered" in result
        assert "owner" in result
        assert "timestamp" in result
        ok("verify_hash (未注册)", f"registered={result['registered']}")

    except ConnectionError as e:
        fail("contract_client", f"无法连接 RPC: {e}")
    except Exception as e:
        fail("contract_client", str(e))


def test_register_and_verify():
    """测试 register_file + verify_file 端到端流程。"""
    section("register_file + verify_file (链上端到端)")
    try:
        import tempfile
        from proof_client.register_file import register_file
        from proof_client.verify_file import verify_file
        from proof_client.config import EVIDENCE_DIR, DB_PATH

        # 创建临时文件
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False,
            dir=str(Path("works")),
            prefix="chain_test_",
        ) as f:
            f.write(f"chain test file - unique content {os.urandom(8).hex()}")
            tmp_path = f.name

        # 1) 注册
        record = register_file(tmp_path)
        assert record.status == "success"
        assert record.tx_hash != ""
        assert record.block_number > 0
        ok("register_file", f"tx=0x{record.tx_hash[:16]}..., block={record.block_number}")

        # 2) 验证
        result = verify_file(tmp_path)
        assert result["registered"] is True
        assert result["chain_data"]["owner"] != "0x" + "0" * 40
        ok("verify_file", f"owner={result['chain_data']['owner'][:16]}...")

        # 3) 本地证据存在
        assert result["local_evidence"] is not None
        ok("本地证据已保存", f"file={result['local_evidence'].file_name}")

        # 清理
        os.unlink(tmp_path)
        evidence_file = EVIDENCE_DIR / f"evidence_{record.file_hash.replace('0x','')[:8]}.json"
        if evidence_file.exists():
            evidence_file.unlink()
        if DB_PATH.exists():
            DB_PATH.unlink()
        ok("清理测试数据")

    except ConnectionError as e:
        fail("register+verify", f"无法连接 RPC: {e}")
    except Exception as e:
        fail("register+verify", str(e))


# ══════════════════════════════════════════════════════════════════
# 第 4 层：报告与查询（依赖已有数据）
# ══════════════════════════════════════════════════════════════════

def test_generate_report():
    """测试 generate_report.py — 报告生成。"""
    section("generate_report.py")
    try:
        from proof_client.evidence_schema import EvidenceRecord
        from proof_client.evidence_store import save_evidence
        from proof_client.generate_report import generate_report
        from proof_client.config import EVIDENCE_DIR, REPORTS_DIR

        test_hash = "0x_test_report_hash_" + "c" * 44

        # 先保存一条证据
        r = EvidenceRecord(
            file_name="report_test.txt",
            file_hash=test_hash,
            uri="sepolia://report_test.txt",
            tx_hash="deadbeef" * 8,
            block_number=99999,
            gas_used=21000,
            owner="0xReportTestOwner",
            timestamp=1718000000,
            status="success",
            contract_address="0xContractAddr",
            explorer_tx_url="https://sepolia.etherscan.io/tx/",
        )
        evidence_path = save_evidence(r)

        # 1) 生成报告
        report_path = generate_report(test_hash)
        assert report_path is not None, "generate_report 应返回路径"
        assert report_path.exists(), "报告文件应存在"
        ok("generate_report", str(report_path.name))

        # 2) 报告内容检查
        content = report_path.read_text(encoding="utf-8")
        assert "report_test.txt" in content
        assert "Proof of Existence" in content
        assert "验证方法" in content
        ok("报告内容正确", f"长度={len(content)} 字符")

        # 3) 不存在的哈希
        result = generate_report("0xnon_existent_" + "d" * 50)
        assert result is None
        ok("generate_report (不存在)", "返回 None")

        # 清理
        evidence_path.unlink()
        report_path.unlink()
        ok("清理测试文件")

    except Exception as e:
        fail("generate_report", str(e))


def test_query_evidence():
    """测试 query_evidence.py — 查询功能。"""
    section("query_evidence.py")
    try:
        from proof_client.evidence_schema import EvidenceRecord
        from proof_client import evidence_repository as repo
        from proof_client.query_evidence import query_all, query_by_hash, query_by_owner, query_stats
        from proof_client.config import DB_PATH

        test_hash = "0x_test_query_hash_" + "e" * 44

        # 插入测试数据
        r = EvidenceRecord(
            file_name="query_test.txt",
            file_hash=test_hash,
            uri="sepolia://query_test.txt",
            owner="0xQueryTestOwner",
            status="success",
        )
        repo.insert(r)

        # 1) query_all (不抛异常即可)
        query_all()
        ok("query_all", "无异常")

        # 2) query_by_hash
        query_by_hash(test_hash)
        ok("query_by_hash", "无异常")

        # 3) query_by_owner
        query_by_owner("0xQueryTestOwner")
        ok("query_by_owner", "无异常")

        # 4) query_stats
        query_stats()
        ok("query_stats", "无异常")

        # 清理
        if DB_PATH.exists():
            DB_PATH.unlink()
        ok("清理测试数据库")

    except Exception as e:
        fail("query_evidence", str(e))


# ══════════════════════════════════════════════════════════════════
# 主入口
# ══════════════════════════════════════════════════════════════════

def main():
    run_chain = "--chain" in sys.argv

    print()
    print("╔══════════════════════════════════════════════════════════╗")
    print("║       proof_client 全模块测试                            ║")
    print(f"║       模式: {'本地 + 链上' if run_chain else '仅本地（不含链上交互）'}                      ║")
    print("╚══════════════════════════════════════════════════════════╝")

    # 第 1 层：纯本地
    test_config()
    test_hash_file()
    test_evidence_schema()
    test_evidence_store()
    test_evidence_repository()

    # 第 2 层：钱包
    test_wallet()

    # 第 3 层：链上交互
    if run_chain:
        test_contract_client()
        test_register_and_verify()
    else:
        section("跳过链上测试 (使用 --chain 启用)")

    # 第 4 层：报告与查询
    test_generate_report()
    test_query_evidence()

    # 汇总
    total = _passed + _failed
    print()
    print("╔══════════════════════════════════════════════════════════╗")
    print(f"║  📊 测试结果: {_passed}/{total} 通过, {_failed} 失败                       ║")
    print("╚══════════════════════════════════════════════════════════╝")

    if _failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
