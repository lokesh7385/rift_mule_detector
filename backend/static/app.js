
// ============================================
// Global State
// ============================================
let analysisData = null;
let networkNodes = [];
let networkEdges = [];
let canvas = null;
let ctx = null;
let fullCanvas = null;
let fullCtx = null;
let animationId = null;
let fullAnimationId = null;
let hoveredNode = null;
let selectedNode = null;
let canvasWidth = 0;
let canvasHeight = 0;
let currentPage = 'overview';

// ============================================
// Initialization
// ============================================
document.addEventListener('DOMContentLoaded', () => {
    initNavigation();
    initClosePanel();
    initSettings();
    initFileUpload();
    if (window.ThemeManager) window.ThemeManager.init();

    // Resize canvas on load
    setTimeout(() => {
        canvas = document.getElementById('networkCanvas');
        if (canvas) {
            ctx = canvas.getContext('2d');
            resizeCanvas(canvas, ctx);
            bindCanvasEvents(canvas, handleOverviewMouseMove, handleOverviewClick);
            animateNetwork(canvas, ctx, animationId);
        }
    }, 100);
});

window.addEventListener('resize', () => {
    if (canvas && ctx) resizeCanvas(canvas, ctx);
    if (fullCanvas && fullCtx) resizeCanvas(fullCanvas, fullCtx);
});

// ============================================
// File Upload Logic
// ============================================
function initFileUpload() {
    const fileInput = document.getElementById('fileInput');
    if (fileInput) {
        fileInput.addEventListener('change', () => {
            if (fileInput.files.length > 0) {
                processFile(fileInput.files[0]);
            }
        });
    }
}

async function processFile(file) {
    const uploadOverlay = document.getElementById('uploadOverlay');
    const loadingOverlay = document.getElementById('loadingOverlay');

    uploadOverlay.classList.add('hidden');
    loadingOverlay.classList.remove('hidden');

    const CHUNK_THRESHOLD = 10 * 1024 * 1024; // 10 MB

    if (file.size <= CHUNK_THRESHOLD) {
        await uploadDirect(file);
    } else {
        await uploadChunked(file);
    }
}

async function uploadDirect(file) {
    const formData = new FormData();
    formData.append('file', file);
    try {
        const response = await fetch('/upload', { method: 'POST', body: formData });
        if (!response.ok) {
            const err = await response.json();
            throw new Error(err.error || 'Upload failed');
        }
        analysisData = await response.json();
        finishUpload();
    } catch (err) {
        handleUploadError(err);
    }
}

async function uploadChunked(file) {
    const CHUNK_SIZE = 2 * 1024 * 1024;
    const totalChunks = Math.ceil(file.size / CHUNK_SIZE);
    let fileId = null;

    const loadingSub = document.querySelector('.loading-sub');
    const progressFill = document.querySelector('.scan-progress-fill');

    for (let i = 0; i < totalChunks; i++) {
        const start = i * CHUNK_SIZE;
        const end = Math.min(start + CHUNK_SIZE, file.size);
        const chunk = file.slice(start, end);
        const formData = new FormData();
        formData.append('file', chunk, file.name);
        formData.append('chunkIndex', i);
        formData.append('totalChunks', totalChunks);
        if (fileId) formData.append('fileId', fileId);

        try {
            const percent = Math.round(((i + 1) / totalChunks) * 100);
            if (loadingSub) loadingSub.textContent = `Uploading part ${i + 1}/${totalChunks} (${percent}%)...`;
            if (progressFill) progressFill.style.width = `${percent}%`;

            const response = await fetch('/upload_chunk', { method: 'POST', body: formData });
            if (!response.ok) {
                const err = await response.json();
                throw new Error(err.error || 'Upload failed');
            }
            const data = await response.json();

            if (i === 0) {
                fileId = data.file_id;
                analysisData = data;
                // Render immediately with partial data
                finishUpload();
                // Show analyzing toast?
            } else if (i === totalChunks - 1) {
                // Done
                pollFullReport(fileId);
            }
        } catch (err) {
            handleUploadError(err);
            return;
        }
    }
}

function finishUpload() {
    const loadingOverlay = document.getElementById('loadingOverlay');
    loadingOverlay.classList.add('hidden');
    renderDashboard();
}

function handleUploadError(err) {
    const loadingOverlay = document.getElementById('loadingOverlay');
    const uploadOverlay = document.getElementById('uploadOverlay');
    loadingOverlay.classList.add('hidden');
    if (!analysisData) uploadOverlay.classList.remove('hidden');
    alert('Error: ' + err.message);
}

// ============================================
// Dashboard Rendering
// ============================================

function viewRingDetails(ringId) {
    if (!analysisData || !analysisData.fraud_rings) return;
    const ring = analysisData.fraud_rings.find(r => r.ring_id === ringId);
    if (!ring) {
        alert("Ring details not found.");
        return;
    }

    const patternName = ring.pattern_type.replace(/_/g, ' ').toUpperCase();
    const txCount = ring.transaction_count !== undefined ? ring.transaction_count : "Calculate on hover";
    const confidence = ring.risk_score;

    // Populate Modal Data
    const scoreElem = document.getElementById('modalScore');
    if (scoreElem) scoreElem.textContent = ring.risk_score + '%';

    const barElem = document.getElementById('modalScoreBar');
    if (barElem) {
        barElem.style.width = ring.risk_score + '%';
        barElem.className = `h-full transition-all duration-1000 ease-out ${ring.risk_score >= 80 ? 'bg-cyber-red' : ring.risk_score >= 50 ? 'bg-cyber-orange' : 'bg-cyber-blue'}`;
    }

    const countElem = document.getElementById('modalTxCount');
    if (countElem) countElem.textContent = ring.transaction_count || 0;

    const typeElem = document.getElementById('modalPatternType');
    if (typeElem) typeElem.textContent = patternName;

    const descElem = document.getElementById('modalDescription');
    if (descElem) descElem.textContent = getFraudDescription(ring.pattern_type);

    // Populate Members
    const membersContainer = document.getElementById('modalMembers');
    if (membersContainer) {
        membersContainer.innerHTML = ring.member_accounts.map(acc => `
            <span class="px-2 py-1 rounded bg-white/5 border border-white/10 text-xs font-mono text-gray-300">
                ${acc}
            </span>
        `).join('');
    }

    openFraudModal();
}

function getFraudDescription(type) {
    if (type === 'cycle') return "Funds moving in a closed loop (A->B->C->A) to inflate volume artificially.";
    if (type === 'fan_out') return "One account distributing funds to many mules (Smurfing/Structuring).";
    if (type === 'fan_in') return "Many mules funneling small amounts into a single aggregator account.";
    if (type === 'layered_shell') return "Complex layering through intermediate shell accounts to hide source.";
    return "Suspicious transaction pattern.";
}


function renderDashboard() {
    if (!analysisData) return;

    // 1. Update Metrics
    const summary = analysisData.summary || {};
    document.getElementById('metric-txns').textContent = (summary.total_transactions || 0).toLocaleString();
    document.getElementById('metric-rings').textContent = (summary.fraud_rings_detected || 0);
    document.getElementById('metric-accounts').textContent = (summary.suspicious_accounts_flagged || 0);
    document.getElementById('metric-time').textContent = (summary.processing_time_seconds || 0) + 's';

    // 2. Update Detection Table
    const tbody = document.getElementById('detectionTable');
    if (tbody && analysisData.fraud_rings) {
        tbody.innerHTML = analysisData.fraud_rings.slice(0, 50).map(ring => {
            const riskScore = ring.risk_score || 0;
            const riskColor = riskScore >= 80 ? '#FF3131' : riskScore >= 50 ? '#FF9500' : '#00D4FF';
            // Assuming first member is ID for now
            const accId = ring.member_accounts[0] || 'Unknown';

            return `
                <tr class="border-b border-white/5">
                    <td class="px-6 py-4"><span class="font-medium">${accId} (+${ring.member_accounts.length - 1})</span></td>
                    <td class="px-6 py-4">
                        <div class="flex items-center gap-3">
                            <span class="font-display font-bold text-lg" style="color: ${riskColor}">${riskScore}</span>
                            <div class="w-20 risk-bar">
                                <div class="risk-bar-fill" style="width: ${riskScore}%; background: ${riskColor};"></div>
                            </div>
                        </div>
                    </td>
                    <td class="px-6 py-4"><span class="px-3 py-1 rounded-full text-xs font-semibold uppercase bg-white/10">${ring.pattern_type}</span></td>
                    <td class="px-6 py-4"><button class="px-4 py-2 rounded-lg text-xs font-semibold bg-white/5 hover:bg-white/10" onclick="viewRingDetails('${ring.ring_id}')">View</button></td>
                </tr>
            `;
        }).join('');
    }

    // 3. Update Graph
    if (analysisData.graph) {
        loadNetworkData(analysisData.graph);
    }

    // 4. Handle Partial State
    const btnFull = document.getElementById('btnFullReport');
    if (summary.is_partial) {
        btnFull.classList.remove('hidden');
        pollFullReport(analysisData.file_id);
    } else {
        btnFull.classList.add('hidden');
    }
}

async function pollFullReport(fileId) {
    const btn = document.getElementById('btnFullReport');
    if (btn) btn.classList.remove('hidden');

    const interval = setInterval(async () => {
        try {
            const res = await fetch(`/full_report/${fileId}`);
            if (res.status === 200) {
                const data = await res.json();
                clearInterval(interval);
                analysisData = data;
                renderDashboard();
                if (btn) btn.classList.add('hidden'); // Hide button when done? Or show "Done"?
                alert("Full Analysis Complete!");
            }
        } catch (e) {
            console.error("Polling error", e);
        }
    }, 2000);
}

function downloadReport() {
    if (!analysisData) {
        alert("No data to download");
        return;
    }
    // Deep copy and remove graph
    const report = JSON.parse(JSON.stringify(analysisData));
    delete report.graph;

    const blob = new Blob([JSON.stringify(report, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `mule_report_${new Date().toISOString().slice(0, 10)}.json`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
}


// ============================================
// Graph Logic (Custom Canvas)
// ============================================
function loadNetworkData(graphData) {
    networkNodes = [];
    networkEdges = [];
    const eps = 0.001;
    const width = canvas ? canvas.width / (window.devicePixelRatio || 1) : 800;
    const height = canvas ? canvas.height / (window.devicePixelRatio || 1) : 600;

    // Create Nodes
    // Graph data nodes: [{id: 'A'}, ...]
    // Map ID to Index for edges
    const idToIndex = {};

    graphData.nodes.forEach((n, i) => {
        idToIndex[n.id] = i;
        const isFraud = n.is_fraud || false;
        networkNodes.push({
            id: n.id,
            x: Math.random() * width,
            y: Math.random() * height,
            vx: (Math.random() - 0.5) * 0.3, // Slower drift
            vy: (Math.random() - 0.5) * 0.3,
            radius: isFraud ? 6 : 4,
            isFraud: isFraud,
            riskScore: n.risk_score || (isFraud ? 85 : 20),
            label: n.id
        });
    });

    // Create Edges
    graphData.edges.forEach(e => {
        const sourceIdx = idToIndex[e.source];
        const targetIdx = idToIndex[e.target];
        if (sourceIdx !== undefined && targetIdx !== undefined) {
            networkEdges.push({
                source: sourceIdx,
                target: targetIdx,
                isFraud: networkNodes[sourceIdx].isFraud || networkNodes[targetIdx].isFraud,
                animOffset: Math.random() * 100
            });
        }
    });
}

function animateNetwork(canvasEl, context, animId) {
    if (!context || !canvasEl) return;

    const width = canvasEl.width / (window.devicePixelRatio || 1);
    const height = canvasEl.height / (window.devicePixelRatio || 1);

    context.clearRect(0, 0, width, height);
    const time = Date.now() * 0.001;

    // Draw edges
    for (const edge of networkEdges) {
        const source = networkNodes[edge.source];
        const target = networkNodes[edge.target];
        if (!source || !target) continue;

        context.beginPath();
        context.moveTo(source.x, source.y);
        context.lineTo(target.x, target.y);

        if (edge.isFraud) {
            context.strokeStyle = 'rgba(255, 49, 49, 0.3)';
            context.lineWidth = 2;
        } else {
            context.strokeStyle = 'rgba(0, 212, 255, 0.15)';
            context.lineWidth = 1;
        }
        context.stroke();

        // Animated data flow particle
        if (edge.isFraud) {
            const progress = ((time * 0.5 + edge.animOffset) % 1);
            const flowX = source.x + (target.x - source.x) * progress;
            const flowY = source.y + (target.y - source.y) * progress;

            context.beginPath();
            const flowRadius = 3;
            context.arc(flowX, flowY, flowRadius, 0, Math.PI * 2);
            context.fillStyle = '#FF3131';
            context.fill();
        }
    }

    // Update & Draw nodes
    for (const node of networkNodes) {
        const isSelected = selectedNode && selectedNode.id === node.id;
        const isHovered = hoveredNode && hoveredNode.id === node.id;
        const nodeRadius = Math.max(0.5, node.radius + (isHovered ? 3 : 0));

        // Update position (Drift & Bounce)
        node.x += node.vx;
        node.y += node.vy;

        // Bounce off edges with margin
        const margin = 20;
        if (node.x < margin || node.x > width - margin) node.vx *= -1;
        if (node.y < margin || node.y > height - margin) node.vy *= -1;

        // Clamp
        node.x = Math.max(margin, Math.min(width - margin, node.x));
        node.y = Math.max(margin, Math.min(height - margin, node.y));

        // Glow effect
        if (node.isFraud || isSelected) {
            const gradient = context.createRadialGradient(
                node.x, node.y, 0,
                node.x, node.y, Math.max(0.5, nodeRadius * 3)
            );
            gradient.addColorStop(0, node.isFraud ? 'rgba(255,49,49,0.4)' : 'rgba(0,212,255,0.4)');
            gradient.addColorStop(1, 'rgba(0,0,0,0)');
            context.beginPath();
            context.arc(node.x, node.y, Math.max(0.5, nodeRadius * 3), 0, Math.PI * 2);
            context.fillStyle = gradient;
            context.fill();
        }

        // Node circle
        context.beginPath();
        context.arc(node.x, node.y, nodeRadius, 0, Math.PI * 2);

        if (node.isFraud) {
            context.fillStyle = '#FF3131';
        } else if (node.riskScore > 50) {
            context.fillStyle = '#FF9500'; // High Risk
        } else {
            context.fillStyle = '#00D4FF'; // Low Risk
        }
        context.fill();

        // Selection ring
        if (isSelected) {
            context.beginPath();
            context.arc(node.x, node.y, Math.max(0.5, nodeRadius + 4), 0, Math.PI * 2);
            context.strokeStyle = '#00D4FF';
            context.lineWidth = 2;
            context.stroke();
        }
    }

    requestAnimationFrame(() => animateNetwork(canvasEl, context, animId));
}

// ============================================
// Helpers from User Code
// ============================================
function initNavigation() {
    const navButtons = document.querySelectorAll('[data-page]');
    navButtons.forEach(btn => {
        btn.addEventListener('click', () => {
            const page = btn.dataset.page;
            switchPage(page);
        });
    });
}

function switchPage(pageName) {
    document.querySelectorAll('[data-page]').forEach(btn => {
        btn.classList.remove('active');
        btn.removeAttribute('aria-current');
        if (btn.dataset.page === pageName) {
            btn.classList.add('active');
            btn.setAttribute('aria-current', 'page');
        }
    });

    document.querySelectorAll('.page-content').forEach(page => page.classList.remove('active'));
    const targetPage = document.getElementById(`page-${pageName}`);
    if (targetPage) setTimeout(() => targetPage.classList.add('active'), 50);

    if (pageName === 'network') initFullNetwork();
}

function resizeCanvas(canvasEl, context) {
    if (!canvasEl || !context) return;
    const rect = canvasEl.parentElement.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    canvasEl.width = rect.width * dpr;
    canvasEl.height = rect.height * dpr;
    canvasEl.style.width = rect.width + 'px';
    canvasEl.style.height = rect.height + 'px';
    context.scale(dpr, dpr);
}

function bindCanvasEvents(canvasEl, moveHandler, clickHandler) {
    if (!canvasEl) return;
    // Simplified: Just basic binding
    canvasEl.addEventListener('mousemove', moveHandler);
    canvasEl.addEventListener('click', clickHandler);
}

function handleOverviewMouseMove(e) {
    if (!canvas) return;
    const rect = canvas.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;

    hoveredNode = null;
    for (const node of networkNodes) {
        const dx = x - node.x;
        const dy = y - node.y;
        const dist = Math.sqrt(dx * dx + dy * dy);
        if (dist < Math.max(1, node.radius + 5)) {
            hoveredNode = node;
            break;
        }
    }

    const tooltip = document.getElementById('nodeTooltip');
    if (hoveredNode && tooltip) {
        tooltip.classList.add('visible');
        tooltip.style.left = `${hoveredNode.x + 15}px`;
        tooltip.style.top = `${hoveredNode.y - 30}px`;
        const idElem = document.getElementById('tooltipId');
        const riskElem = document.getElementById('tooltipRisk');
        if (idElem) idElem.textContent = hoveredNode.label;
        if (riskElem) riskElem.textContent = `Risk Score: ${hoveredNode.riskScore}`;
    } else if (tooltip) {
        tooltip.classList.remove('visible');
    }

    // Changing canvas style directly here works if bound to canvas
    // Or we rely on parent container cursor style if specific
    canvas.style.cursor = hoveredNode ? 'pointer' : 'crosshair';
}

function handleOverviewClick(e) {
    if (hoveredNode) {
        selectedNode = hoveredNode;
        showActionPanel(hoveredNode);
    } else {
        selectedNode = null;
        const panel = document.getElementById('actionPanel');
        if (panel) panel.classList.remove('open');
    }
}

function showActionPanel(node) {
    const panel = document.getElementById('actionPanel');
    const content = document.getElementById('panelContent');
    if (!panel || !content) return;

    panel.classList.add('open');

    const riskLevel = node.riskScore >= 80 ? 'Critical' : node.riskScore >= 50 ? 'High' : 'Moderate';
    const riskColor = node.riskScore >= 80 ? '#FF3131' : node.riskScore >= 50 ? '#FF9500' : '#00D4FF';

    content.innerHTML = `
        <div class="space-y-6 animate-reveal">
            <!-- Account Header -->
            <div class="text-center">
                <div class="w-16 h-16 rounded-full mx-auto mb-4 flex items-center justify-center" style="background: ${riskColor}20;">
                    <span class="font-display font-bold text-xl" style="color: ${riskColor}">${node.label.slice(-4)}</span>
                </div>
                <h4 class="font-display font-bold text-xl">${node.label}</h4>
                <p class="text-sm text-gray-500 mt-1">${node.isFraud ? 'Fraud Ring Member' : 'Standard Account'}</p>
            </div>
            
            <!-- Risk Score -->
            <div class="glass rounded-xl p-4">
                <div class="flex items-center justify-between mb-2">
                    <span class="text-sm text-gray-400">Risk Score</span>
                    <span class="font-display font-bold text-2xl" style="color: ${riskColor}">${node.riskScore}</span>
                </div>
                <div class="risk-bar">
                    <div class="risk-bar-fill" style="width: ${node.riskScore}%; background: ${riskColor};"></div>
                </div>
                <p class="text-xs mt-2 font-medium" style="color: ${riskColor}">${riskLevel} Risk</p>
            </div>

            <!-- Meta Data (Mocked for now) -->
             <div class="grid grid-cols-2 gap-3">
                <div class="glass rounded-lg p-3 text-center">
                    <p class="text-xs text-gray-500">Connections</p>
                    <p class="font-display font-bold text-lg">${Math.floor(Math.random() * 15) + 3}</p>
                </div>
                <div class="glass rounded-lg p-3 text-center">
                    <p class="text-xs text-gray-500">Volume (30d)</p>
                    <p class="font-display font-bold text-lg">$${(Math.random() * 500).toFixed(1)}K</p>
                </div>
            </div>
            
            <!-- Actions -->
            <div class="space-y-3 pt-4 border-t border-white/5">
                <button class="btn-danger w-full py-3 rounded-xl flex items-center justify-center gap-2" onclick="alert('Account ${node.label} frozen')">
                    <svg class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z"/>
                    </svg>
                    Freeze Account
                </button>
            </div>
        </div>
    `;
}

function initClosePanel() {
    const closeBtn = document.getElementById('closePanel');
    const panel = document.getElementById('actionPanel');
    if (closeBtn && panel) closeBtn.addEventListener('click', () => panel.classList.remove('open'));
}

function initSettings() {
    // Placeholder
}

function initFullNetwork() {
    fullCanvas = document.getElementById('fullNetworkCanvas');
    if (fullCanvas) {
        fullCtx = fullCanvas.getContext('2d');
        resizeCanvas(fullCanvas, fullCtx);
        // Use global networkNodes/Edges
        animateNetwork(fullCanvas, fullCtx, fullAnimationId);
    }
}

// ============================================
// Theme Manager (Celestial Switch)
// ============================================
window.ThemeManager = {
    init() {
        const savedTheme = localStorage.getItem('mulewatch-theme');
        // Default to Dark
        const isDark = savedTheme ? savedTheme === 'dark' : true;

        this.applyTheme(isDark);
        this.bindEvents();
    },

    applyTheme(isDark) {
        const body = document.body;
        const toggle = document.getElementById('celestialToggle');

        // 1. Update Body Theme
        if (isDark) {
            body.classList.remove('light-theme');
        } else {
            body.classList.add('light-theme');
        }

        // 2. Update Switch Visual State
        if (toggle) {
            if (isDark) {
                toggle.classList.add('dark');
                toggle.setAttribute('aria-checked', 'true');
            } else {
                toggle.classList.remove('dark');
                toggle.setAttribute('aria-checked', 'false');
            }
        }

        localStorage.setItem('mulewatch-theme', isDark ? 'dark' : 'light');
    },

    toggle() {
        const isCurrentlyDark = document.body.classList.contains('light-theme') === false;
        this.applyTheme(!isCurrentlyDark);
    },

    bindEvents() {
        const toggle = document.getElementById('celestialToggle');
        if (toggle) {
            toggle.addEventListener('click', () => this.toggle());
            toggle.addEventListener('keydown', (e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    this.toggle();
                }
            });
        }
    }
};

function openFraudModal() {
    const modal = document.getElementById('fraudModal');
    const backdrop = document.getElementById('modalBackdrop');
    const content = document.getElementById('modalContent');
    
    if (modal) {
        modal.classList.remove('hidden');
        // Trigger reflow
        void modal.offsetWidth;
        
        if (backdrop) backdrop.classList.remove('opacity-0');
        if (content) content.classList.remove('opacity-0', 'scale-95');
    }
}

function closeFraudModal() {
    const modal = document.getElementById('fraudModal');
    const backdrop = document.getElementById('modalBackdrop');
    const content = document.getElementById('modalContent');
    
    if (modal) {
        if (backdrop) backdrop.classList.add('opacity-0');
        if (content) content.classList.add('opacity-0', 'scale-95');
        
        setTimeout(() => {
            modal.classList.add('hidden');
        }, 300);
    }
}

document.addEventListener('DOMContentLoaded', () => {
    const backdrop = document.getElementById('modalBackdrop');
    if(backdrop) {
        backdrop.addEventListener('click', closeFraudModal);
    }
});

