#!/usr/bin/env python3
"""
MV最適化ダッシュボード - FastAPI バックエンド

HTML版ダッシュボードにデータを提供するAPIサーバー。

起動方法:
    cd experiments/small_test_ver2/scripts
    source ../../../.venv/bin/activate
    uvicorn dashboard_api:app --host 0.0.0.0 --port 8000 --reload

SSHポートフォワード:
    ssh -L 8000:localhost:8000 user@server
    → ブラウザで http://localhost:8000 を開く
"""

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse
from pathlib import Path
import json
import re
from typing import List, Dict, Any, Optional

app = FastAPI(title="MV最適化ダッシュボード API")

# ディレクトリパス
SCRIPT_DIR = Path(__file__).resolve().parent
EXP_DIR = SCRIPT_DIR.parent
OUTPUT_DIR = EXP_DIR / "time_dependent_output"
JSON_DIR = EXP_DIR / "02_json"
STATIC_DIR = SCRIPT_DIR / "dashboard_static"


def natural_sort_key(s):
    """自然数ソート用のキー関数"""
    return [int(text) if text.isdigit() else text.lower() 
            for text in re.split(r'(\d+)', str(s))]


# 静的ファイルをマウント（存在する場合）
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
async def root():
    """ダッシュボードHTMLを返す"""
    html_path = SCRIPT_DIR / "dashboard.html"
    if html_path.exists():
        return FileResponse(html_path)
    return HTMLResponse("<h1>dashboard.html not found</h1>")


@app.get("/api/query-sets")
async def get_query_sets() -> List[str]:
    """利用可能なクエリセットを取得"""
    if not OUTPUT_DIR.exists():
        return []
    query_sets = [d.name for d in OUTPUT_DIR.iterdir() 
                  if d.is_dir() and not d.name.startswith('.') 
                  and d.name not in ['log', 'store_result', 'migration_plan']]
    return sorted(query_sets, key=natural_sort_key)


@app.get("/api/result-files/{query_set}")
async def get_result_files(query_set: str) -> Dict[str, List[str]]:
    """結果ファイル一覧を取得"""
    output_path = OUTPUT_DIR / query_set
    if not output_path.exists():
        raise HTTPException(status_code=404, detail="Query set not found")
    
    opt_files = [f.name for f in sorted(output_path.glob("td_mv_optimization_result_*.json"), 
                                         key=lambda f: natural_sort_key(f.name))]
    bench_files = [f.name for f in sorted(output_path.glob("benchmark_results_*.json"),
                                          key=lambda f: natural_sort_key(f.name))]
    static_files = [f.name for f in sorted(output_path.glob("static_mv_optimization_result_*.json"),
                                           key=lambda f: natural_sort_key(f.name))]
    
    return {
        "optimization": opt_files,
        "benchmark": bench_files,
        "static": static_files
    }


@app.get("/api/optimization-result/{query_set}/{filename}")
async def get_optimization_result(query_set: str, filename: str) -> Dict:
    """最適化結果を取得"""
    filepath = OUTPUT_DIR / query_set / filename
    if not filepath.exists():
        raise HTTPException(status_code=404, detail="File not found")
    
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # migration_analysisからMV詳細を抽出
    processed_timesteps = []
    if 'migration_analysis' in data:
        for t_result in data['migration_analysis']:
            timestep = t_result.get('timestep', 0)
            mvs = t_result.get('selected_mvs', [])
            total_size = t_result.get('total_size', 0)
            mv_count = t_result.get('mv_count', len(mvs))
            
            # creation_detailsから詳細情報を取得
            mv_details = []
            creation_details = {}
            if 'initial_creation' in t_result and 'creation_details' in t_result['initial_creation']:
                for detail in t_result['initial_creation']['creation_details']:
                    creation_details[detail['mv']] = detail
            
            for mv in mvs:
                if isinstance(mv, str):
                    if mv in creation_details:
                        mv_details.append(creation_details[mv])
                    else:
                        est_size = total_size / mv_count if mv_count > 0 else 0
                        mv_details.append({'mv': mv, 'size': est_size, 'cost': 0})
                else:
                    mv_details.append(mv)
            
            # MV名でソート
            mv_details.sort(key=lambda x: natural_sort_key(x.get('mv', '')))
            
            processed_timesteps.append({
                'timestep': int(timestep) if str(timestep).isdigit() else timestep,
                'mvs': mv_details,
                'mv_count': mv_count,
                'total_size': total_size,
                'storage_budget': t_result.get('storage_budget', 0),
                'utilization_percent': t_result.get('utilization_percent', 0)
            })
    
    # タイムステップでソート
    processed_timesteps.sort(key=lambda x: x['timestep'])
    
    return {
        'timesteps': [str(t['timestep']) for t in processed_timesteps],
        'timestep_data': processed_timesteps,
        'summary': data.get('summary', {}),
        'objective': data.get('objective'),
        'workload_cost': data.get('workload_cost'),
        'migration_cost': data.get('migration_cost')
    }


@app.get("/api/queries/{query_set}")
async def get_queries(query_set: str) -> List[str]:
    """クエリ一覧を取得"""
    json_dir = JSON_DIR / query_set
    if not json_dir.exists():
        raise HTTPException(status_code=404, detail="Query set not found")
    
    query_names = [f.stem for f in json_dir.glob("*.json")]
    return sorted(query_names, key=natural_sort_key)


@app.get("/api/explain/{query_set}/{query_name}")
async def get_explain(query_set: str, query_name: str) -> Dict:
    """EXPLAIN JSONを取得"""
    filepath = JSON_DIR / query_set / f"{query_name}.json"
    if not filepath.exists():
        raise HTTPException(status_code=404, detail="File not found")
    
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # PostgreSQLのEXPLAIN出力は配列の最初の要素
    if isinstance(data, list) and len(data) > 0:
        return data[0]
    return data


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
