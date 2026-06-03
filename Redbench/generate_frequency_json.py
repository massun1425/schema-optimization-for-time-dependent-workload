#!/usr/bin/env python3
"""
instance=53のワークロードから時間帯別クエリ頻度JSONを生成

1週間を指定期間数（8 or 14など）に分割し、各期間における各クエリの実行頻度を計算
"""

import json
from datetime import datetime, timedelta
from collections import defaultdict
import sys

def load_workload(queries_json_path):
    """ワークロードファイルを読み込み"""
    print(f"ワークロードファイルを読み込み中: {queries_json_path}")
    with open(queries_json_path, 'r') as f:
        data = json.load(f)
    print(f"  総クエリ数: {len(data):,}")
    return data

def analyze_time_range(queries_data):
    """ワークロードの時間範囲を分析"""
    timestamps = []
    for query in queries_data:
        if 'arrival_timestamp' in query:
            ts = datetime.fromisoformat(query['arrival_timestamp'].replace('Z', '+00:00'))
            timestamps.append(ts)
    
    if not timestamps:
        print("エラー: タイムスタンプが見つかりません")
        return None, None
    
    min_ts = min(timestamps)
    max_ts = max(timestamps)
    duration = max_ts - min_ts
    
    print(f"\n時間範囲:")
    print(f"  開始: {min_ts}")
    print(f"  終了: {max_ts}")
    print(f"  期間: {duration}")
    print(f"  日数: {duration.days}日 {duration.seconds // 3600}時間")
    
    return min_ts, max_ts

def calculate_frequency_by_period(queries_data, num_periods, period_type='week'):
    """
    期間ごとのクエリ頻度を計算
    
    Args:
        queries_data: クエリデータ
        num_periods: 分割する期間数（8, 14, 24など）
        period_type: 'week' (1週間ベース) or 'day' (1日ベース)
    """
    print(f"\n{num_periods}期間での頻度を計算中...")
    
    # タイムスタンプごとにクエリを分類
    min_ts, max_ts = analyze_time_range(queries_data)
    if not min_ts:
        return None
    
    # 全期間の長さを計算
    total_duration = max_ts - min_ts
    
    if period_type == 'week':
        # 1週間（7日）を基準とする
        base_duration = timedelta(days=7)
        period_duration = base_duration / num_periods
        # 実際のデータ期間が1週間より長い場合は、最初の1週間のみ使用
        if total_duration > base_duration:
            print(f"  注意: データ期間が{total_duration.days}日ありますが、最初の7日間のみ使用します")
            max_ts = min_ts + base_duration
    elif period_type == 'day':
        # 1日（24時間）を基準とする
        base_duration = timedelta(days=1)
        period_duration = base_duration / num_periods
        if total_duration > base_duration:
            print(f"  注意: データ期間が{total_duration.days}日ありますが、最初の1日のみ使用します")
            max_ts = min_ts + base_duration
    elif period_type == 'full':
        # 全期間を使用して均等分割
        print(f"  全期間（{total_duration.days}日）を{num_periods}期間に分割します")
        period_duration = total_duration / num_periods
        print(f"  各期間: 約{period_duration.days}日 {period_duration.seconds // 3600}時間")
    else:
        # 全期間を均等分割
        period_duration = total_duration / num_periods
    
    print(f"  期間長: {period_duration}")
    
    # 各期間ごとのクエリカウント
    query_counts = defaultdict(lambda: [0] * num_periods)
    total_counts_per_period = [0] * num_periods
    
    for query in queries_data:
        if 'arrival_timestamp' not in query or 'filepath' not in query:
            continue
        
        ts = datetime.fromisoformat(query['arrival_timestamp'].replace('Z', '+00:00'))
        
        # 範囲外のクエリはスキップ
        if ts < min_ts or ts >= max_ts:
            continue
        
        # どの期間に属するかを計算
        elapsed = ts - min_ts
        period_idx = int(elapsed / period_duration)
        
        # 最後の期間を超えないようにクリップ
        period_idx = min(period_idx, num_periods - 1)
        
        # filepathからクエリ名を抽出（例: "output/tmp_matching/imdb/benchmarks/job/3c.sql" -> "3c.sql"）
        import os
        query_name = os.path.basename(query['filepath'])
        query_counts[query_name][period_idx] += 1
        total_counts_per_period[period_idx] += 1
    
    print(f"\n各期間のクエリ数:")
    for i, count in enumerate(total_counts_per_period):
        print(f"  期間{i+1}: {count:,}クエリ")
    
    print(f"\nユニーククエリ種類: {len(query_counts)}")
    
    return query_counts, total_counts_per_period

def normalize_frequencies(query_counts, total_counts_per_period, normalization='binary'):
    """
    頻度を正規化
    
    Args:
        normalization: 
            - 'binary': 0 or 1（その期間に実行されたか）
            - 'relative': 全期間での最大値を1とする相対値
            - 'count': 実行回数そのまま
    """
    normalized = {}
    
    for query_name, counts in query_counts.items():
        if normalization == 'binary':
            # 1回でも実行されていれば1、なければ0
            normalized[query_name] = [1 if c > 0 else 0 for c in counts]
        elif normalization == 'relative':
            # そのクエリの全期間での最大値で正規化
            max_count = max(counts) if max(counts) > 0 else 1
            normalized[query_name] = [c / max_count for c in counts]
        elif normalization == 'count':
            # 実行回数そのまま
            normalized[query_name] = counts
        else:
            raise ValueError(f"Unknown normalization: {normalization}")
    
    return normalized

def save_frequency_json(frequency_data, output_path, description, num_periods):
    """頻度データをJSON形式で保存"""
    
    output = {
        "description": description,
        "note": f"Frequency data for {num_periods} time periods based on actual workload execution patterns",
        "queries": {}
    }
    
    # クエリ名でソート
    for query_name in sorted(frequency_data.keys()):
        output["queries"][query_name] = frequency_data[query_name]
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    
    print(f"\n✅ 保存完了: {output_path}")
    print(f"   クエリ数: {len(frequency_data)}")

def main():
    # 設定
    queries_json_path = "output/generated_workloads/imdb/serverless/cluster_53/database_1/matching_1d251c0ce20b00ace653b4e602d75063/queries.json"
    
    # ワークロード読み込み
    queries_data = load_workload(queries_json_path)
    
    print("\n" + "=" * 80)
    print("期間分割オプション")
    print("=" * 80)
    print("1. 8期間（1週間ベース - 最初の7日間のみ）")
    print("2. 14期間（1週間を12時間ごと - 最初の7日間のみ）")
    print("3. 24期間（1日を1時間ごと - 最初の24時間のみ）")
    print("4. 8期間（全期間を週単位で分割）← instance=53全期間用")
    print("5. カスタム")
    
    choice = input("\n選択してください [1-5, デフォルト=4]: ").strip() or "4"
    
    if choice == "1":
        num_periods = 8
        period_type = 'week'
        output_name = "frequency_redbench_instance53_8periods.json"
        description = "RedBench instance=53 Frequency (1 week, 8 periods)"
    elif choice == "2":
        num_periods = 14
        period_type = 'week'
        output_name = "frequency_redbench_instance53_14periods.json"
        description = "RedBench instance=53 Frequency (1 week, 14 periods of 12 hours)"
    elif choice == "3":
        num_periods = 24
        period_type = 'day'
        output_name = "frequency_redbench_instance53_24periods.json"
        description = "RedBench instance=53 Frequency (1 day, 24 hours)"
    elif choice == "4":
        num_periods = 8
        period_type = 'full'
        output_name = "frequency_redbench_instance53_8weeks.json"
        description = "RedBench instance=53 Frequency (Full period, 8 weeks)"
    else:
        num_periods = int(input("期間数を入力: "))
        period_type_input = input("タイプ (week/day/full) [full]: ").strip() or 'full'
        period_type = period_type_input
        output_name = f"frequency_redbench_instance53_{num_periods}periods_{period_type}.json"
        description = f"RedBench instance=53 Frequency ({num_periods} periods, {period_type})"
    
    # 頻度計算
    query_counts, total_counts = calculate_frequency_by_period(
        queries_data, num_periods, period_type
    )
    
    if not query_counts:
        print("エラー: 頻度計算に失敗しました")
        return
    
    print("\n" + "=" * 80)
    print("正規化方法")
    print("=" * 80)
    print("1. binary: 0 or 1（実行されたかどうか）")
    print("2. relative: 相対頻度（各クエリの最大値を1とする）")
    print("3. count: 実行回数そのまま ← instance=53週単位用")
    
    norm_choice = input("\n選択してください [1-3, デフォルト=3]: ").strip() or "3"
    
    if norm_choice == "1":
        normalization = 'binary'
    elif norm_choice == "2":
        normalization = 'relative'
    else:
        normalization = 'count'
    
    # 正規化
    frequency_data = normalize_frequencies(query_counts, total_counts, normalization)
    
    # サンプル表示
    print("\n" + "=" * 80)
    print("頻度データのサンプル（最初の10クエリ）")
    print("=" * 80)
    for i, (query_name, freqs) in enumerate(sorted(frequency_data.items())[:10]):
        print(f"{query_name}: {freqs}")
    
    # 保存
    save_frequency_json(frequency_data, output_name, description, num_periods)
    
    print("\n" + "=" * 80)
    print("完了")
    print("=" * 80)

if __name__ == "__main__":
    main()
