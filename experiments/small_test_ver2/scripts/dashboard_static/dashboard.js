// グローバル状態
let currentQuerySet = null;
let currentResultFile = null;
let optimizationData = null;
let staticOptimizationData = null; // 静的最適化データ保持用
let benchmarkData = null; // ベンチマークデータ保持用
let comparisonSelectedFiles = new Set(); // 比較用選択ファイル
let selectedMVs = [];

// 自然数ソート
function naturalSort(arr) {
    return arr.sort((a, b) => {
        const ax = [], bx = [];
        a.replace(/(\d+)|(\D+)/g, (_, $1, $2) => { ax.push([$1 || Infinity, $2 || ""]) });
        b.replace(/(\d+)|(\D+)/g, (_, $1, $2) => { bx.push([$1 || Infinity, $2 || ""]) });
        while (ax.length && bx.length) {
            const an = ax.shift(), bn = bx.shift();
            const nn = (an[0] - bn[0]) || an[1].localeCompare(bn[1]);
            if (nn) return nn;
        }
        return ax.length - bx.length;
    });
}


// バイトを人間が読める形式に変換
function formatBytes(bytes) {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

// API呼び出しヘルパー
async function fetchAPI(endpoint) {
    const response = await fetch(endpoint);
    if (!response.ok) throw new Error(`API error: ${response.status}`);
    return response.json();
}

// 初期化
async function init() {
    // クエリセット読み込み
    const querySets = await fetchAPI('/api/query-sets');
    const querySetSelect = document.getElementById('query-set-select');
    querySets.forEach(qs => {
        const opt = document.createElement('option');
        opt.value = qs;
        opt.textContent = qs;
        querySetSelect.appendChild(opt);
    });

    // デフォルト選択
    if (querySets.includes('job')) {
        querySetSelect.value = 'job';
    }

    querySetSelect.addEventListener('change', onQuerySetChange);
    await onQuerySetChange();

    // タブ切り替え
    document.querySelectorAll('.tab').forEach(tab => {
        tab.addEventListener('click', () => {
            document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
            document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
            tab.classList.add('active');
            document.getElementById(tab.dataset.tab).classList.add('active');

            // クエリツリータブに切り替えたときは再描画
            if (tab.dataset.tab === 'query-tree') {
                setTimeout(() => updateQueryTree(), 100);
            }
            // 比較タブ切り替え時
            if (tab.dataset.tab === 'comparison') {
                renderComparisonFileList();
            }
        });
    });

    // 比較更新ボタン
    document.getElementById('update-comparison-btn').addEventListener('click', updateComparisonCharts);

    // スライダー初期化
    setupSlider('timestep-slider', 'timestep-value', '', onTimestepChange);
    setupSlider('table-height', 'table-height-value', 'px', v => {
        document.getElementById('mv-table-container').style.height = v + 'px';
    });
}

function setupSlider(sliderId, valueId, suffix, onChange) {
    const slider = document.getElementById(sliderId);
    const valueEl = document.getElementById(valueId);
    slider.addEventListener('input', () => {
        valueEl.textContent = slider.value + suffix;
        onChange(parseInt(slider.value));
    });
}

// クエリセット変更
async function onQuerySetChange() {
    currentQuerySet = document.getElementById('query-set-select').value;

    // サブフォルダ読み込み
    const subfolders = await fetchAPI(`/api/subfolders/${currentQuerySet}`);
    const subfolderSelect = document.getElementById('subfolder-select');
    subfolderSelect.innerHTML = '';

    if (subfolders.length === 0) {
        // サブフォルダがない場合は非表示
        const opt = document.createElement('option');
        opt.value = '';
        opt.textContent = '(なし)';
        subfolderSelect.appendChild(opt);
    } else {
        subfolders.forEach(sf => {
            const opt = document.createElement('option');
            opt.value = sf;
            opt.textContent = sf;
            subfolderSelect.appendChild(opt);
        });
    }

    subfolderSelect.addEventListener('change', onSubfolderChange);
    await onSubfolderChange();

    // クエリ一覧読み込み
    const queries = await fetchAPI(`/api/queries/${currentQuerySet}`);
    const querySelect = document.getElementById('query-select');
    querySelect.innerHTML = '';
    queries.forEach(q => {
        const opt = document.createElement('option');
        opt.value = q;
        opt.textContent = q;
        querySelect.appendChild(opt);
    });
    querySelect.addEventListener('change', updateQueryTree);
}

// サブフォルダ変更
async function onSubfolderChange() {
    const subfolder = document.getElementById('subfolder-select').value;

    // 結果ファイル読み込み
    const files = await fetchAPI(`/api/result-files/${currentQuerySet}?subfolder=${encodeURIComponent(subfolder)}`);
    const resultSelect = document.getElementById('result-file-select');
    resultSelect.innerHTML = '';

    // 動的最適化ファイル
    files.optimization.forEach(f => {
        const opt = document.createElement('option');
        opt.value = f;
        opt.textContent = `[動的] ${f}`;
        opt.dataset.type = 'dynamic';
        resultSelect.appendChild(opt);
    });

    // 静的最適化ファイル
    files.static.forEach(f => {
        const opt = document.createElement('option');
        opt.value = f;
        opt.textContent = `[静的] ${f}`;
        opt.dataset.type = 'static';
        resultSelect.appendChild(opt);
    });

    resultSelect.addEventListener('change', onResultFileChange);

    // 比較リストの更新と選択状態のリセット
    comparisonSelectedFiles.clear();
    renderComparisonFileList();

    await onResultFileChange();
}

// 結果ファイル変更
async function onResultFileChange() {
    const resultSelect = document.getElementById('result-file-select');
    currentResultFile = resultSelect.value;
    if (!currentResultFile) return;

    const subfolder = document.getElementById('subfolder-select').value;
    const selectedOption = resultSelect.options[resultSelect.selectedIndex];
    const fileType = selectedOption?.dataset?.type || 'dynamic';

    // スライダーコンテナを取得
    const sliderContainer = document.querySelector('.slider-container');

    // 時系列分析パネルのID
    const timeSeriesPanels = ['panel-changes-summary', 'panel-storage-chart', 'panel-mv-timeline'];

    if (fileType === 'static') {
        // 静的最適化結果を取得
        const staticData = await fetchAPI(`/api/static-result/${currentQuerySet}/${currentResultFile}?subfolder=${encodeURIComponent(subfolder)}`);

        // タイムステップスライダーを非表示
        sliderContainer.style.display = 'none';

        // 時系列パネルを非表示
        timeSeriesPanels.forEach(id => {
            const el = document.getElementById(id);
            if (el) el.style.display = 'none';
        });

        // メトリクス更新
        document.getElementById('mv-count').textContent = staticData.mv_count;
        document.getElementById('total-size').textContent = formatBytes(staticData.total_size);
        document.getElementById('total-cost').textContent = staticData.objective_value.toFixed(2);
        document.getElementById('utilization').textContent = staticData.utilization_percent.toFixed(1) + '%';

        // 選択されたMVを更新
        selectedMVs = staticData.selected_mvs;

        // テーブル更新
        const tbody = document.getElementById('mv-table-body');
        tbody.innerHTML = '';
        staticData.mv_details.forEach(mv => {
            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td>${mv.mv}</td>
                <td>${formatBytes(mv.size || 0)}</td>
                <td>${(mv.cost || 0).toFixed(2)}</td>
            `;
            tbody.appendChild(tr);
        });

        // グローバル変数に保存
        staticOptimizationData = staticData;
        optimizationData = null; // 動的データはクリア

        // クエリツリーのタイムステップ選択を非表示
        document.getElementById('tree-timestep-select').parentElement.style.display = 'none';

    } else {
        // 動的最適化結果を取得（従来の処理）
        // 動的最適化結果を取得（従来の処理）
        optimizationData = await fetchAPI(`/api/optimization-result/${currentQuerySet}/${currentResultFile}?subfolder=${encodeURIComponent(subfolder)}`);
        staticOptimizationData = null;

        // タイムステップスライダーを表示
        sliderContainer.style.display = 'flex';

        // 時系列パネルを表示
        timeSeriesPanels.forEach(id => {
            const el = document.getElementById(id);
            if (el) el.style.display = 'block';
        });

        // クエリツリーのタイムステップ選択を表示
        document.getElementById('tree-timestep-select').parentElement.style.display = 'inline-block';

        // スライダー更新
        const slider = document.getElementById('timestep-slider');
        slider.max = optimizationData.timesteps.length - 1;
        slider.value = 0;
        document.getElementById('timestep-value').textContent = '0';

        // タイムステップセレクト更新
        const tsSelect = document.getElementById('tree-timestep-select');
        tsSelect.innerHTML = '';
        optimizationData.timesteps.forEach((t, i) => {
            const opt = document.createElement('option');
            opt.value = i;
            opt.textContent = `T${t}`;
            tsSelect.appendChild(opt);
        });
        tsSelect.addEventListener('change', updateQueryTree);

        // 各ビュー更新
        onTimestepChange(0);
        updateTimelineChart();
        updateStorageChart();
        updateChangesTable();
    }

    // ベンチマーク結果取得 & 更新
    try {
        benchmarkData = await fetchAPI(`/api/benchmark-result/${currentQuerySet}/${currentResultFile}?subfolder=${encodeURIComponent(subfolder)}`);
        updateBenchmarkChart();
    } catch (e) {
        console.warn("Benchmark data fetch failed:", e);
        benchmarkData = null;
        updateBenchmarkChart(); // クリア表示
    }

    updateQueryTree();
}

// タイムステップ変更
function onTimestepChange(timestep) {
    if (!optimizationData) return;

    const tsData = optimizationData.timestep_data[timestep];
    if (!tsData) return;

    selectedMVs = tsData.mvs.map(m => m.mv);

    // メトリクス更新
    document.getElementById('mv-count').textContent = tsData.mv_count;
    document.getElementById('total-size').textContent = formatBytes(tsData.total_size);
    const totalCost = tsData.mvs.reduce((sum, m) => sum + (m.cost || 0), 0);
    document.getElementById('total-cost').textContent = totalCost.toFixed(2);
    document.getElementById('utilization').textContent = tsData.utilization_percent.toFixed(1) + '%';

    // テーブル更新
    const tbody = document.getElementById('mv-table-body');
    tbody.innerHTML = '';
    tsData.mvs.forEach(mv => {
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td>${mv.mv}</td>
            <td>${formatBytes(mv.size || 0)}</td>
            <td>${(mv.cost || 0).toFixed(2)}</td>
        `;
        tbody.appendChild(tr);
    });
}

// タイムラインチャート更新
function updateTimelineChart() {
    if (!optimizationData) return;

    // MVごとの選択状態をマトリクス化
    const allMVs = new Set();
    optimizationData.timestep_data.forEach(ts => {
        ts.mvs.forEach(m => allMVs.add(m.mv));
    });
    const mvList = naturalSort([...allMVs]);

    // MV数に応じてチャート高さを計算（各MV行に25px、最小400px）
    const chartHeight = Math.max(400, mvList.length * 25 + 80);
    document.getElementById('timeline-chart').style.height = chartHeight + 'px';

    const z = mvList.map(mv =>
        optimizationData.timestep_data.map(ts =>
            ts.mvs.some(m => m.mv === mv) ? 1 : 0
        )
    );

    const data = [{
        z: z,
        x: optimizationData.timesteps.map(t => 'T' + t),
        y: mvList,
        type: 'heatmap',
        colorscale: [[0, '#313244'], [1, '#a6e3a1']],
        showscale: false,
        xgap: 1,  // セル間の水平ギャップ
        ygap: 1   // セル間の垂直ギャップ（MV間の境界線）
    }];

    const layout = {
        paper_bgcolor: 'rgba(0,0,0,0)',
        plot_bgcolor: '#1e1e2e',
        font: { color: '#cdd6f4' },
        margin: { l: 120, r: 20, t: 20, b: 40 },
        xaxis: { title: 'タイムステップ' },
        yaxis: { title: '', autorange: 'reversed' },
        height: chartHeight
    };

    Plotly.newPlot('timeline-chart', data, layout, { responsive: true });
}

// ストレージチャート更新
function updateStorageChart() {
    if (!optimizationData) return;

    const data = [{
        x: optimizationData.timesteps.map(t => parseInt(t)),
        y: optimizationData.timestep_data.map(ts => ts.total_size / (1024 * 1024)),
        type: 'scatter',
        mode: 'lines+markers',
        fill: 'tozeroy',
        fillcolor: 'rgba(137, 180, 250, 0.2)',
        line: { color: '#89b4fa', width: 2 },
        marker: { size: 6 }
    }];

    const layout = {
        paper_bgcolor: 'rgba(0,0,0,0)',
        plot_bgcolor: '#1e1e2e',
        font: { color: '#cdd6f4' },
        margin: { l: 60, r: 20, t: 20, b: 40 },
        xaxis: { title: 'タイムステップ' },
        yaxis: { title: 'ストレージ (MB)' }
    };

    Plotly.newPlot('storage-chart', data, layout, { responsive: true });
}

// 変更テーブル更新
function updateChangesTable() {
    if (!optimizationData) return;

    const tbody = document.getElementById('changes-table-body');
    tbody.innerHTML = '';

    let prevMVs = new Set();
    optimizationData.timestep_data.forEach(ts => {
        const currentMVs = new Set(ts.mvs.map(m => m.mv));
        const added = [...currentMVs].filter(m => !prevMVs.has(m));
        const removed = [...prevMVs].filter(m => !currentMVs.has(m));

        if (added.length > 0 || removed.length > 0) {
            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td>T${ts.timestep}</td>
                <td style="color: var(--accent-green)">+${added.length}</td>
                <td style="color: var(--accent-red)">-${removed.length}</td>
            `;
            tbody.appendChild(tr);
        }
        prevMVs = currentMVs;
    });
}

// クエリツリー更新
async function updateQueryTree() {
    const queryName = document.getElementById('query-select').value;
    const timestep = parseInt(document.getElementById('tree-timestep-select').value || 0);

    if (!queryName || !currentQuerySet) return;

    // EXPLAIN取得
    const explain = await fetchAPI(`/api/explain/${currentQuerySet}/${queryName}`);

    // 選択MVリストを取得
    let allSelectedMVs = [];

    // 静的最適化の場合（staticOptimizationDataが存在）
    if (staticOptimizationData) {
        allSelectedMVs = staticOptimizationData.selected_mvs || [];
    } else if (optimizationData && optimizationData.timestep_data[timestep]) {
        // 動的最適化の場合、選択されたタイムステップのMVを使用
        allSelectedMVs = optimizationData.timestep_data[timestep].mvs.map(m => m.mv);
    }

    // クエリ固有のMV使用情報を取得（包含関係フィルタ済み）
    try {
        const mvUsage = await fetchAPI(
            `/api/query-mv-usage/${currentQuerySet}/${queryName}?selected_mvs=${allSelectedMVs.join(',')}`
        );
        // このクエリで実際に使用されるMVのみをハイライト対象に
        selectedMVs = mvUsage.usable_mvs;
        console.log(`Query ${queryName}: uses ${mvUsage.total_usable_mvs} MVs out of ${allSelectedMVs.length} selected`);
    } catch (e) {
        // フォールバック: qp_class.pklがない場合は全MVを使用
        console.warn('query-mv-usage API failed, falling back to all MVs:', e);
        selectedMVs = allSelectedMVs;
    }

    renderTree(explain);
}

// D3.jsでツリー描画（縦方向: 上から下）
function renderTree(planData) {
    const container = document.getElementById('tree-container');
    const svg = d3.select('#tree-svg');
    svg.selectAll('*').remove();

    const width = container.clientWidth - 40;
    const height = container.clientHeight - 40;

    // ツリーデータ構築
    function buildHierarchy(node) {
        const result = {
            name: node['Node Type'],
            nodeId: node.node_id || '',
            relation: node['Relation Name'] || '',
            alias: node['Alias'] || '',
            rows: node['Plan Rows'] || 0,
            cost: node['Total Cost'] || 0,
            children: []
        };
        if (node.Plans) {
            result.children = node.Plans.map(buildHierarchy);
        }
        return result;
    }

    const plan = planData.Plan || planData;
    const root = d3.hierarchy(buildHierarchy(plan));

    // ツリーの深さとリーフ数を計算
    const depth = root.height;
    const leaves = root.leaves().length;

    // 木の深さに基づいてSVG高さを計算（各レベル間に十分な間隔を確保）
    const nodeSpacing = 60;  // ノード間の垂直間隔
    const treeHeight = Math.max(400, (depth + 1) * nodeSpacing);

    // 幅はコンテナに収める
    const treeWidth = width - 60;

    // 縦方向ツリーレイアウト
    const treeLayout = d3.tree()
        .size([treeWidth, treeHeight])
        .separation((a, b) => (a.parent === b.parent ? 1 : 1.5));
    treeLayout(root);

    // SVGサイズを木のサイズに合わせる
    svg.attr('width', width).attr('height', treeHeight + 60);

    const g = svg.append('g').attr('transform', 'translate(30, 30)');

    // リンク描画（縦方向）
    g.selectAll('.link')
        .data(root.links())
        .join('path')
        .attr('class', 'link')
        .attr('d', d3.linkVertical()
            .x(d => d.x)
            .y(d => d.y));

    // ノード描画
    const node = g.selectAll('.node')
        .data(root.descendants())
        .join('g')
        .attr('class', 'node')
        .attr('transform', d => `translate(${d.x},${d.y})`);

    node.append('rect')
        .attr('x', -45)
        .attr('y', -18)
        .attr('width', 90)
        .attr('height', 36)
        .attr('rx', 4)
        .attr('fill', d => {
            if (selectedMVs.includes(d.data.nodeId)) return '#a6e3a1';
            if (d.data.nodeId.startsWith('leaf_')) return '#fab387';
            if (d.data.nodeId.startsWith('non_leaf_')) return '#89b4fa';
            return '#cdd6f4';
        })
        .attr('stroke', d => selectedMVs.includes(d.data.nodeId) ? '#fff' : 'none')
        .attr('stroke-width', 2);

    // ノードタイプ（1行目）
    node.append('text')
        .attr('dy', -5)
        .attr('text-anchor', 'middle')
        .attr('fill', '#1e1e2e')
        .attr('font-size', '7px')
        .attr('font-weight', '600')
        .text(d => d.data.name);

    // テーブル名またはノードID（2行目）
    node.append('text')
        .attr('dy', 5)
        .attr('text-anchor', 'middle')
        .attr('fill', '#1e1e2e')
        .attr('font-size', '6px')
        .text(d => d.data.relation ? `${d.data.relation}` : d.data.nodeId);

    // コスト（3行目）
    node.append('text')
        .attr('dy', 13)
        .attr('text-anchor', 'middle')
        .attr('fill', '#1e1e2e')
        .attr('font-size', '5px')
        .attr('opacity', 0.8)
        .text(d => `cost: ${d.data.cost.toFixed(0)}`);
}

// ベンチマークチャート更新
function updateBenchmarkChart() {
    if (!benchmarkData || !benchmarkData.found) {
        document.getElementById('benchmark-chart').innerHTML = '<div class="loading">No benchmark data</div>';
        document.getElementById('benchmark-line-chart').innerHTML = '';
        ['total-exec-time', 'total-query-time', 'total-migration-time'].forEach(id => {
            document.getElementById(id).textContent = '-';
        });
        return;
    }

    // サマリー更新
    document.getElementById('total-exec-time').textContent = benchmarkData.total_execution_time.toFixed(2);
    document.getElementById('total-query-time').textContent = benchmarkData.total_query_time.toFixed(2);
    document.getElementById('total-migration-time').textContent = benchmarkData.total_migration_time.toFixed(2);

    // チャートデータ作成
    const timesteps = benchmarkData.timesteps.map(t => 'T' + t.timestep);
    const queryTimes = benchmarkData.timesteps.map(t => t.query_time);
    const migrationTimes = benchmarkData.timesteps.map(t => t.migration_time);

    // 1. 積み上げ棒グラフ (Query vs Migration)
    const trace1 = {
        x: timesteps,
        y: queryTimes,
        name: 'クエリ実行時間',
        type: 'bar',
        marker: { color: '#89b4fa' },
        text: queryTimes.map(t => t > 0 ? t.toFixed(2) : ''),
        textposition: 'auto',
        textfont: { color: '#1e1e2e' }
    };

    const trace2 = {
        x: timesteps,
        y: migrationTimes,
        name: 'マイグレーション時間',
        type: 'bar',
        marker: { color: '#f38ba8' },
        text: migrationTimes.map(t => t > 0 ? t.toFixed(2) : ''),
        textposition: 'auto',
        textfont: { color: '#1e1e2e' }
    };

    const barLayout = {
        barmode: 'stack',
        paper_bgcolor: 'rgba(0,0,0,0)',
        plot_bgcolor: '#1e1e2e',
        font: { color: '#cdd6f4' },
        margin: { l: 60, r: 20, t: 30, b: 40 },
        xaxis: { title: 'タイムステップ' },
        yaxis: { title: '時間 (秒)' },
        legend: { orientation: 'h', y: 1.1 }
    };

    Plotly.newPlot('benchmark-chart', [trace1, trace2], barLayout, { responsive: true });

    // 2. 折れ線グラフ (Query Time Trend)
    const traceLine = {
        x: timesteps,
        y: queryTimes,
        name: 'クエリ時間推移',
        type: 'scatter',
        mode: 'lines+markers+text',
        line: { color: '#a6e3a1', width: 2 },
        marker: { size: 6, color: '#a6e3a1' },
        text: queryTimes.map(t => t > 0 ? t.toFixed(2) : ''),
        textposition: 'top center',
        textfont: { color: '#a6e3a1' } // テキスト色をラインに合わせる
    };

    const lineLayout = {
        paper_bgcolor: 'rgba(0,0,0,0)',
        plot_bgcolor: '#1e1e2e',
        font: { color: '#cdd6f4' },
        margin: { l: 60, r: 20, t: 30, b: 40 },
        xaxis: { title: 'タイムステップ' },
        yaxis: { title: 'クエリ実行時間 (秒)' },
        showlegend: false
    };

    Plotly.newPlot('benchmark-line-chart', [traceLine], lineLayout, { responsive: true });
}

// 比較用ファイルリスト描画
function renderComparisonFileList() {
    const container = document.getElementById('comparison-file-list');
    container.innerHTML = '';

    const resultSelect = document.getElementById('result-file-select');
    // result-file-selectのオプションを使用（すでにサブフォルダでフィルタされている前提）
    if (resultSelect.options.length === 0) {
        container.textContent = '結果ファイルがありません';
        return;
    }

    // 全選択/解除チェックボックス
    const allLabel = document.createElement('label');
    allLabel.style.display = 'block';
    allLabel.style.marginBottom = '8px';
    allLabel.style.fontWeight = 'bold';
    allLabel.innerHTML = `<input type="checkbox" id="comparison-select-all"> 全て選択`;
    container.appendChild(allLabel);

    document.getElementById('comparison-select-all').addEventListener('change', (e) => {
        const checked = e.target.checked;
        container.querySelectorAll('.comp-file-checkbox').forEach(cb => {
            cb.checked = checked;
            if (checked) comparisonSelectedFiles.add(cb.value);
            else comparisonSelectedFiles.delete(cb.value);
        });
    });

    Array.from(resultSelect.options).forEach(opt => {
        const div = document.createElement('div');
        div.style.marginBottom = '4px';

        const checkbox = document.createElement('input');
        checkbox.type = 'checkbox';
        checkbox.className = 'comp-file-checkbox';
        checkbox.value = opt.value;
        checkbox.dataset.type = opt.dataset.type; // static or dynamic
        checkbox.checked = comparisonSelectedFiles.has(opt.value);

        checkbox.addEventListener('change', (e) => {
            if (e.target.checked) comparisonSelectedFiles.add(opt.value);
            else comparisonSelectedFiles.delete(opt.value);
        });

        const label = document.createElement('label');
        label.appendChild(checkbox);
        label.appendChild(document.createTextNode(' ' + opt.text));
        label.style.cursor = 'pointer';

        div.appendChild(label);
        container.appendChild(div);
    });
}

// 比較チャート更新
async function updateComparisonCharts() {
    if (comparisonSelectedFiles.size === 0) {
        alert('比較するファイルを選択してください');
        return;
    }

    const subfolder = document.getElementById('subfolder-select').value;
    const files = Array.from(comparisonSelectedFiles);

    // データ並列取得
    const results = await Promise.all(files.map(async file => {
        try {
            const data = await fetchAPI(`/api/benchmark-result/${currentQuerySet}/${file}?subfolder=${encodeURIComponent(subfolder)}`);
            return { file, data };
        } catch (e) {
            console.error(`Failed to fetch ${file}:`, e);
            return { file, data: null };
        }
    }));

    const validResults = results.filter(r => r.data && r.data.found);
    if (validResults.length === 0) return;

    // カラーパレット
    const colors = [
        '#89b4fa', '#f38ba8', '#a6e3a1', '#fab387', '#cba6f7',
        '#f5c2e7', '#94e2d5', '#f9e2af', '#74c7ec', '#b4befe'
    ];

    // ファイル名短縮ヘルパー
    const shortenName = (name) => name.replace(/benchmark_results_|_opt\.json/g, '').replace(/^static_|dynamic_/, '');

    // 0. サマリーテーブル更新
    const summaryBody = document.querySelector('#comparison-summary-table tbody');
    summaryBody.innerHTML = '';
    validResults.forEach(r => {
        const row = document.createElement('tr');
        row.innerHTML = `
            <td style="font-weight: bold;">${shortenName(r.file)}</td>
            <td>${r.data.total_execution_time.toFixed(2)}</td>
            <td>${r.data.total_query_time.toFixed(2)}</td>
            <td>${r.data.total_migration_time.toFixed(2)}</td>
        `;
        summaryBody.appendChild(row);
    });

    // 1. 棒グラフ (Stacked + Grouped by Timestep using Multicategory)
    // X軸構造: [Timestep, Method]
    const allTimesteps = new Set();
    validResults.forEach(r => r.data.timesteps.forEach(t => allTimesteps.add(t.timestep)));
    // 数値としてソート
    const sortedTimesteps = Array.from(allTimesteps).sort((a, b) => a - b);

    const xTimesteps = [];
    const xMethods = [];
    const yQuery = [];
    const yMigration = [];
    const colorQuery = [];
    const colorMigration = [];

    // データフラット化
    sortedTimesteps.forEach(ts => {
        validResults.forEach((r, i) => {
            const tsData = r.data.timesteps.find(d => d.timestep === ts);
            // データがない場合も空（0）として入れる
            const qTime = tsData ? tsData.query_time : 0;
            const mTime = tsData ? tsData.migration_time : 0;
            const name = shortenName(r.file);
            const color = colors[i % colors.length];

            xTimesteps.push('T' + ts);
            xMethods.push(name);
            yQuery.push(qTime);
            yMigration.push(mTime);
            colorQuery.push(color);
            colorMigration.push(color);
        });
    });

    const stackTraceQuery = {
        x: [xTimesteps, xMethods],
        y: yQuery,
        name: 'クエリ時間', // 凡例用だが、色は個別指定しているので凡例と色が一致しない問題がある
        type: 'bar',
        marker: { color: colorQuery },
        showlegend: false, // 色がバラバラなので凡例は消す（またはダミーを作る）
        text: yQuery.map(t => t > 0 ? t.toFixed(1) : ''),
        textposition: 'auto',
        hoverinfo: 'y'
    };

    const stackTraceMigration = {
        x: [xTimesteps, xMethods],
        y: yMigration,
        name: 'マイグレーション時間',
        type: 'bar',
        marker: { color: colorMigration, opacity: 0.4 }, // 薄くする
        showlegend: false,
        text: yMigration.map(t => t > 0 ? t.toFixed(1) : ''),
        textposition: 'auto',
        hoverinfo: 'y'
    };

    const barLayout = {
        title: 'ベンチマーク詳細比較 (濃:クエリ, 薄:マイグレーション)',
        barmode: 'stack', // 各手法内でクエリとマイグレーションを積み上げ
        paper_bgcolor: 'rgba(0,0,0,0)',
        plot_bgcolor: '#1e1e2e',
        font: { color: '#cdd6f4' },
        margin: { l: 60, r: 20, t: 30, b: 80 }, // 下余白多めに
        xaxis: {
            title: 'タイムステップ / 手法',
            tickangle: -45
        },
        yaxis: { title: '実行時間 (秒)' },
        showlegend: false
    };

    Plotly.newPlot('comparison-bar-chart', [stackTraceQuery, stackTraceMigration], barLayout, { responsive: true });

    // 2. 折れ線グラフ (Query Time Trend)
    const lineTraces = validResults.map((r, i) => {
        const timesteps = r.data.timesteps.map(t => 'T' + t.timestep);
        const queryTimes = r.data.timesteps.map(t => t.query_time);

        return {
            x: timesteps,
            y: queryTimes,
            name: shortenName(r.file),
            type: 'scatter',
            mode: 'lines+markers',
            line: { color: colors[i % colors.length], width: 2 },
            marker: { size: 6 }
        };
    });

    const lineLayout = {
        paper_bgcolor: 'rgba(0,0,0,0)',
        plot_bgcolor: '#1e1e2e',
        font: { color: '#cdd6f4' },
        margin: { l: 60, r: 20, t: 30, b: 40 },
        xaxis: { title: 'タイムステップ' },
        yaxis: { title: 'クエリ実行時間 (秒)' },
        showlegend: true,
        legend: { orientation: 'h', y: 1.1 }
    };

    Plotly.newPlot('comparison-line-chart', lineTraces, lineLayout, { responsive: true });
}

// 初期化実行
init().catch(console.error);
