#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CIL Router 测试运行器
提供便捷的测试执行命令，支持不同类型和级别的测试
"""

import sys
import subprocess
import argparse
from pathlib import Path

class TestRunner:
    """测试运行器"""
    
    def __init__(self):
        self.root_dir = Path(__file__).parent
        self.test_dir = self.root_dir / "test_suites"
    
    def run_unit_tests(self, verbose=False):
        """运行单元测试"""
        print("🧪 运行单元测试...")
        return self._run_pytest(self.test_dir / "unit", verbose)
    
    def run_integration_tests(self, verbose=False):
        """运行集成测试"""
        print("🔗 运行集成测试...")
        return self._run_pytest(self.test_dir / "integration", verbose)
    
    def run_stress_tests(self, verbose=False):
        """运行压力测试"""
        print("💪 运行压力测试...")
        return self._run_pytest(self.test_dir / "stress", verbose)
    
    def run_security_tests(self, verbose=False):
        """运行安全测试"""
        print("🛡️ 运行安全测试...")
        return self._run_pytest(self.test_dir / "security", verbose)
    
    def run_performance_tests(self, verbose=False):
        """运行性能测试"""
        print("🚀 运行性能测试...")
        perf_dir = self.test_dir / "performance"
        if not any(perf_dir.glob("test_*.py")):
            print("   📝 暂无性能测试文件")
            return True
        return self._run_pytest(perf_dir, verbose)
    
    def run_all_tests(self, verbose=False):
        """运行所有测试"""
        print("🎯 运行所有测试...")
        return self._run_pytest(self.test_dir, verbose)
    
    def run_quick_tests(self, verbose=False):
        """运行快速测试（单元测试 + 部分集成测试）"""
        print("⚡ 运行快速测试...")
        success = True
        success &= self.run_unit_tests(verbose)
        
        # 运行关键的集成测试
        key_integration_tests = [
            "test_final_integration.py"
        ]
        for test_file in key_integration_tests:
            test_path = self.test_dir / "integration" / test_file
            if test_path.exists():
                success &= self._run_pytest(test_path, verbose)
        
        return success
    
    def generate_report(self):
        """生成测试报告"""
        print("📊 生成综合测试报告...")
        report_script = self.test_dir / "reports" / "comprehensive_test_report.py"
        
        if report_script.exists():
            try:
                result = subprocess.run([
                    sys.executable, str(report_script)
                ], capture_output=True, text=True)
                
                if result.returncode == 0:
                    print("✅ 测试报告生成成功")
                    print(result.stdout)
                    return True
                else:
                    print("❌ 测试报告生成失败")
                    print(result.stderr)
                    return False
            except Exception as e:
                print(f"❌ 运行报告生成器时出错: {e}")
                return False
        else:
            print("⚠️ 测试报告生成器不存在")
            return False
    
    def _run_pytest(self, path, verbose=False):
        """运行pytest"""
        cmd = [sys.executable, "-m", "pytest", str(path)]
        
        if verbose:
            cmd.append("-v")
        else:
            cmd.append("-q")
        
        cmd.extend(["--tb=short", "--no-header"])
        
        try:
            result = subprocess.run(cmd, cwd=self.root_dir)
            return result.returncode == 0
        except Exception as e:
            print(f"❌ 运行测试时出错: {e}")
            return False
    
    def list_test_files(self):
        """列出所有测试文件"""
        print("📋 测试文件列表:")
        
        categories = [
            ("unit", "🧪 单元测试"),
            ("integration", "🔗 集成测试"),
            ("stress", "💪 压力测试"),
            ("security", "🛡️ 安全测试"),
            ("performance", "🚀 性能测试")
        ]
        
        for category, title in categories:
            cat_dir = self.test_dir / category
            if cat_dir.exists():
                test_files = list(cat_dir.glob("test_*.py"))
                if test_files:
                    print(f"\n{title}:")
                    for test_file in sorted(test_files):
                        print(f"   - {test_file.name}")
                else:
                    print(f"\n{title}: 📝 暂无测试文件")
    
    def check_environment(self):
        """检查测试环境"""
        print("🔍 检查测试环境...")
        
        # 检查Python版本
        print(f"Python版本: {sys.version}")
        
        # 检查依赖包
        try:
            import pytest
            print(f"pytest版本: {pytest.__version__}")
        except ImportError:
            print("❌ pytest未安装")
            return False
        
        try:
            import fastapi
            print(f"FastAPI版本: {fastapi.__version__}")
        except ImportError:
            print("❌ FastAPI未安装")
            return False
        
        # 检查测试目录
        if not self.test_dir.exists():
            print(f"❌ 测试目录不存在: {self.test_dir}")
            return False
        
        print("✅ 测试环境检查通过")
        return True


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="CIL Router 测试运行器")
    parser.add_argument("action", choices=[
        "unit", "integration", "stress", "security", "performance",
        "all", "quick", "report", "list", "check"
    ], help="测试动作")
    parser.add_argument("-v", "--verbose", action="store_true", help="详细输出")
    
    args = parser.parse_args()
    
    runner = TestRunner()
    
    print("🔥 CIL Router 测试运行器")
    print("=" * 50)
    
    if args.action == "check":
        success = runner.check_environment()
    elif args.action == "list":
        runner.list_test_files()
        success = True
    elif args.action == "unit":
        success = runner.run_unit_tests(args.verbose)
    elif args.action == "integration":
        success = runner.run_integration_tests(args.verbose)
    elif args.action == "stress":
        success = runner.run_stress_tests(args.verbose)
    elif args.action == "security":
        success = runner.run_security_tests(args.verbose)
    elif args.action == "performance":
        success = runner.run_performance_tests(args.verbose)
    elif args.action == "all":
        success = runner.run_all_tests(args.verbose)
    elif args.action == "quick":
        success = runner.run_quick_tests(args.verbose)
    elif args.action == "report":
        success = runner.generate_report()
    else:
        print(f"❌ 不支持的动作: {args.action}")
        success = False
    
    print("=" * 50)
    if success:
        print("🎉 操作完成")
        sys.exit(0)
    else:
        print("❌ 操作失败")
        sys.exit(1)


if __name__ == "__main__":
    main()