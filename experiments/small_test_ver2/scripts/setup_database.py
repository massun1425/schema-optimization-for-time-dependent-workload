#!/usr/bin/env python3
"""
データベースセットアップスクリプト
small_test または IMDb データベースを選択してセットアップできます
"""

import os
import sys
import argparse
import subprocess
from pathlib import Path

# プロジェクトルートを追加
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

def setup_small_test_db(psql_path: str = "psql", user: str = "postgres"):
    """小規模テストデータベースをセットアップ"""
    setup_file = project_root / "experiments" / "small_test_ver2" / "00_setup.sql"
    
    if not setup_file.exists():
        print(f"❌ エラー: {setup_file} が見つかりません")
        return False
    
    print("=" * 60)
    print("小規模テストデータベース (mv_small_test) のセットアップを開始します")
    print("=" * 60)
    
    try:
        cmd = [psql_path, "-U", user, "-f", str(setup_file)]
        print(f"実行コマンド: {' '.join(cmd)}")
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        print(result.stdout)
        if result.stderr:
            print("警告/エラー出力:", result.stderr)
        
        print("\n✅ 小規模テストデータベースのセットアップが完了しました")
        print("   データベース名: mv_small_test")
        print(f"   テーブル数: 3 (users, products, orders)")
        return True
        
    except subprocess.CalledProcessError as e:
        print(f"❌ エラー: セットアップに失敗しました")
        print(f"エラーコード: {e.returncode}")
        print(f"標準出力: {e.stdout}")
        print(f"標準エラー出力: {e.stderr}")
        return False
    except FileNotFoundError:
        print(f"❌ エラー: psql コマンドが見つかりません ({psql_path})")
        print("PostgreSQL がインストールされているか、パスが正しいか確認してください")
        return False


def setup_imdb_db(psql_path: str = "psql", user: str = "postgres", data_dir: Path = None):
    """IMDb データベースをセットアップ"""
    if data_dir is None:
        data_dir = project_root / "data"
    
    schema_file = data_dir / "schema.sql"
    setup_file = data_dir / "setup.sql"
    
    if not schema_file.exists():
        print(f"❌ エラー: {schema_file} が見つかりません")
        return False
    
    if not setup_file.exists():
        print(f"❌ エラー: {setup_file} が見つかりません")
        return False
    
    print("=" * 60)
    print("IMDb データベース (imdbload) のセットアップを開始します")
    print("=" * 60)
    print(f"データディレクトリ: {data_dir}")
    print()
    
    # ステップ1: データベース作成
    print("ステップ1: データベースを作成します...")
    try:
        create_db_cmd = [
            psql_path, "-U", user, "-c",
            "DROP DATABASE IF EXISTS imdbload; CREATE DATABASE imdbload;"
        ]
        result = subprocess.run(create_db_cmd, check=True, capture_output=True, text=True)
        print("✅ データベース imdbload を作成しました")
    except subprocess.CalledProcessError as e:
        print(f"❌ データベース作成に失敗: {e.stderr}")
        return False
    
    # ステップ2: スキーマ作成
    print("\nステップ2: スキーマを作成します...")
    try:
        schema_cmd = [psql_path, "-U", user, "-d", "imdbload", "-f", str(schema_file)]
        result = subprocess.run(schema_cmd, check=True, capture_output=True, text=True)
        print("✅ スキーマを作成しました")
    except subprocess.CalledProcessError as e:
        print(f"❌ スキーマ作成に失敗: {e.stderr}")
        return False
    
    # ステップ3: データのロード
    print("\nステップ3: データをロードします...")
    print("⚠️  注意: CSVファイルが data/ ディレクトリに存在する必要があります")
    print("   (aka_name.csv, aka_title.csv, cast_info.csv, ...)")
    print()
    
    # data ディレクトリに移動してデータをロード
    try:
        # カレントディレクトリを data に変更
        original_dir = os.getcwd()
        os.chdir(data_dir)
        
        load_cmd = [psql_path, "-U", user, "-d", "imdbload", "-f", "setup.sql"]
        result = subprocess.run(load_cmd, check=True, capture_output=True, text=True)
        
        # 元のディレクトリに戻る
        os.chdir(original_dir)
        
        print(result.stdout)
        if result.stderr and "COPY" in result.stderr:
            print("データロード結果:", result.stderr)
        
        print("\n✅ IMDb データベースのセットアップが完了しました")
        print("   データベース名: imdbload")
        print(f"   スキーマファイル: {schema_file.name}")
        return True
        
    except subprocess.CalledProcessError as e:
        os.chdir(original_dir)  # エラー時も元に戻す
        print(f"❌ エラー: データロードに失敗しました")
        print(f"標準エラー出力: {e.stderr}")
        print("\nヒント: CSVファイルが data/ ディレクトリに存在するか確認してください")
        return False
    except FileNotFoundError:
        os.chdir(original_dir)
        print(f"❌ エラー: psql コマンドが見つかりません ({psql_path})")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="データベースセットアップスクリプト",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用例:
  # 小規模テストデータベースをセットアップ
  python setup_database.py --type small_test
  
  # IMDb データベースをセットアップ
  python setup_database.py --type imdb
  
  # カスタムpsqlパスとユーザーを指定
  python setup_database.py --type imdb --psql-path "C:\\Program Files\\PostgreSQL\\18\\bin\\psql.exe" --user myuser
        """
    )
    
    parser.add_argument(
        "--type",
        choices=["small_test", "imdb"],
        required=True,
        help="セットアップするデータベースタイプ"
    )
    
    parser.add_argument(
        "--psql-path",
        default="psql",
        help="psql コマンドのパス (デフォルト: psql)"
    )
    
    parser.add_argument(
        "--user",
        default="postgres",
        help="PostgreSQL ユーザー名 (デフォルト: postgres)"
    )
    
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=None,
        help="IMDb データディレクトリのパス (デフォルト: プロジェクトルート/data)"
    )
    
    args = parser.parse_args()
    
    print("\n" + "=" * 60)
    print("データベースセットアップスクリプト")
    print("=" * 60)
    print(f"データベースタイプ: {args.type}")
    print(f"PostgreSQL ユーザー: {args.user}")
    print(f"psql パス: {args.psql_path}")
    print()
    
    if args.type == "small_test":
        success = setup_small_test_db(args.psql_path, args.user)
    else:  # imdb
        success = setup_imdb_db(args.psql_path, args.user, args.data_dir)
    
    if success:
        print("\n" + "=" * 60)
        print("✅ セットアップが正常に完了しました")
        print("=" * 60)
        
        # config.yaml の設定を推奨
        config_path = project_root / "experiments" / "small_test_ver2" / "config.yaml"
        print(f"\n次のステップ:")
        print(f"1. {config_path} を編集")
        if args.type == "small_test":
            print(f"   database_type: small_test")
            print(f"   database: mv_small_test")
        else:
            print(f"   database_type: imdb")
            print(f"   database: imdbload")
        print(f"2. 実験スクリプトを実行")
        
        sys.exit(0)
    else:
        print("\n" + "=" * 60)
        print("❌ セットアップに失敗しました")
        print("=" * 60)
        sys.exit(1)


if __name__ == "__main__":
    main()
