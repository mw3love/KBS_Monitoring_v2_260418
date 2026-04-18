// ================================================================
// Video area + ROI overlays + System log panel
// ================================================================
const { useState: useStateP, useEffect: useEffectP } = React;

function VideoArea({ showROI, alertActive, variant }) {
  return (
    <div className="video-area">
      <div className="video-placeholder">NO SIGNAL INPUT</div>
      {showROI && (
        <>
          <div className="roi" style={{ top: '15%', left: '10%', width: '28%', height: '40%' }}>
            <div className="roi-label">V1 [1TV]</div>
          </div>
          <div className={`roi ${alertActive ? 'alert-state' : ''}`} style={{ top: '20%', right: '12%', width: '22%', height: '30%' }}>
            <div className="roi-label">V2 [2TV]</div>
          </div>
          <div className="roi" style={{ bottom: '12%', left: '18%', width: '18%', height: '20%' }}>
            <div className="roi-label">A1 [1TV]</div>
          </div>
          <div className="roi" style={{ bottom: '15%', right: '22%', width: '16%', height: '18%' }}>
            <div className="roi-label">A2 [2TV]</div>
          </div>
        </>
      )}
    </div>
  );
}

function LogPanel({ alertActive }) {
  const baseRows = [
    { t: '18:29:14', tag: 'SYSTEM', msg: '프로그램 시작', cls: 'sys' },
    { t: '18:23:16', tag: 'AUDIO', msg: '오디오 스트림 시작 (테스트톱 활성)', cls: 'audio' },
    { t: '18:23:31', tag: 'SYSTEM', msg: '감지 시작', cls: 'sys' },
    { t: '18:24:02', tag: 'VIDEO', msg: 'V1 [1TV] 블랙 감지 — 3.2초 지속', cls: 'still' },
    { t: '18:24:18', tag: 'AUDIO', msg: 'A1 [1TV] 레벨 정상 복귀', cls: 'audio' },
    { t: '18:25:07', tag: 'EMBED', msg: 'EA1 임베디드 무음 감지 (-54dB)', cls: 'embedded' },
    { t: '18:25:41', tag: 'SYSTEM', msg: 'ROI 재설정 완료', cls: 'sys' },
    { t: '18:26:03', tag: 'VIDEO', msg: 'V2 [2TV] 스틸 감지 복구', cls: 'still' },
    { t: '18:26:55', tag: 'EMBED', msg: 'EA1 임베디드 오디오 정상', cls: 'embedded' },
    { t: '18:27:22', tag: 'AUDIO', msg: 'A2 [2TV] HSV 임계 도달', cls: 'audio' },
  ];

  const [rows, setRows] = useStateP(baseRows);

  useEffectP(() => {
    if (!alertActive) return;
    const id = setTimeout(() => {
      const now = new Date();
      const pad = n => String(n).padStart(2, '0');
      setRows(r => [
        { t: `${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())}`, tag: 'SYSTEM', msg: '감지 투브 응답 감지 (health check) — 마지막 감지: 7초 전', cls: 'error', newest: true },
        ...r.map(x => ({ ...x, newest: false }))
      ]);
    }, 500);
    return () => clearTimeout(id);
  }, [alertActive]);

  return (
    <div className="log-panel">
      <div className="log-header">
        <span className="log-title">SYSTEM LOG</span>
        <span className="log-count">{rows.length} entries</span>
        <div className="log-icons">
          <button className="log-icon-btn" title="폴더 열기">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>
            </svg>
          </button>
          <button className="log-icon-btn" title="Log 추가보기">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>
            </svg>
          </button>
        </div>
      </div>
      <div className="log-body">
        <div className="log-day-sep">── 2026-04-18 ──</div>
        {rows.map((r, i) => (
          <div key={i} className={`log-row ${r.cls} ${r.newest ? 'newest' : ''}`}>
            <span className="ts">{r.t}</span>
            <span className="tag">{r.tag}</span>
            <span className="msg">{r.msg}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

// Left rail for V3 variant
function LeftRail() {
  return (
    <div className="left-rail">
      <div className="lr-section">
        <div className="lr-title">시스템 리소스</div>
        <div className="lr-metric"><span>CPU</span><span className="v">55%</span></div>
        <div className="lr-metric"><span>RAM</span><span className="v">77%</span></div>
        <div className="lr-metric"><span>GPU</span><span className="v">N/A</span></div>
        <div className="lr-metric"><span>Uptime</span><span className="v">3d 12h</span></div>
        <div className="lr-metric"><span>FPS</span><span className="v">29.97</span></div>
      </div>
      <div className="lr-section">
        <div className="lr-title">감지 대상 (6)</div>
        <div className="lr-metric"><span>V1 [1TV]</span><span className="v" style={{color: '#2f9e44'}}>●</span></div>
        <div className="lr-metric"><span>V2 [2TV]</span><span className="v" style={{color: '#e03131'}}>●</span></div>
        <div className="lr-metric"><span>A1 [1TV]</span><span className="v" style={{color: '#2f9e44'}}>●</span></div>
        <div className="lr-metric"><span>A2 [2TV]</span><span className="v" style={{color: '#2f9e44'}}>●</span></div>
        <div className="lr-metric"><span>EA1</span><span className="v" style={{color: '#e03131'}}>●</span></div>
        <div className="lr-metric"><span>EA2</span><span className="v" style={{color: '#2f9e44'}}>●</span></div>
      </div>
      <div className="lr-section">
        <div className="lr-title">정파 스케줄</div>
        <div className="lr-metric"><span>1TV 정파</span><span className="v">03:30</span></div>
        <div className="lr-metric"><span>1TV 재개</span><span className="v">05:00</span></div>
        <div className="lr-metric"><span>2TV 정파</span><span className="v">02:00</span></div>
        <div className="lr-metric"><span>2TV 재개</span><span className="v">05:00</span></div>
      </div>
      <div className="lr-section">
        <div className="lr-title">녹화 상태</div>
        <div className="lr-metric"><span>저장된 파일</span><span className="v">142</span></div>
        <div className="lr-metric"><span>디스크 사용</span><span className="v">37%</span></div>
        <div className="lr-metric"><span>보관 기간</span><span className="v">7일</span></div>
      </div>
    </div>
  );
}

window.VideoArea = VideoArea;
window.LogPanel = LogPanel;
window.LeftRail = LeftRail;
