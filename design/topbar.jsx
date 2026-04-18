// ================================================================
// TopBar — matches original layout density, groups in one row
// ================================================================
const { useState, useEffect, useRef } = React;

function TopBar({ alertActive, muted, setMuted, detOn, setDetOn, showROI, setShowROI, ackPressed, setAckPressed, nightMode, setNightMode, openSettings, variant }) {
  const [meterL, setMeterL] = useState(6);
  const [meterR, setMeterR] = useState(4);
  const [clock, setClock] = useState(new Date());
  const [sig1, setSig1] = useState({ h: 2, m: 14, s: 33 });
  const [sig2, setSig2] = useState({ d: 1, h: 6, m: 6, s: 26 });

  useEffect(() => {
    const t = setInterval(() => {
      setMeterL(Math.floor(5 + Math.random() * 5));
      setMeterR(Math.floor(4 + Math.random() * 5));
      setClock(new Date());
      setSig1(c => {
        let s = c.s - 1, m = c.m, h = c.h;
        if (s < 0) { s = 59; m -= 1; }
        if (m < 0) { m = 59; h -= 1; }
        if (h < 0) { h = 2; m = 14; s = 33; }
        return { h, m, s };
      });
    }, 1000);
    return () => clearInterval(t);
  }, []);

  const pad = n => String(n).padStart(2, '0');
  const hh = pad(clock.getHours()), mm = pad(clock.getMinutes()), ss = pad(clock.getSeconds());
  const c1 = `[${pad(sig1.h)}:${pad(sig1.m)}:${pad(sig1.s)}]`;
  const c2 = `${sig2.d}D [${pad(sig2.h)}:${pad(sig2.m)}:${pad(sig2.s)}]`;

  const segs = (n) => {
    const arr = [];
    for (let i = 0; i < 10; i++) {
      const on = i < n;
      const peak = i >= 8 && on;
      arr.push(<div key={i} className={`seg ${on ? 'on' : ''} ${peak ? 'peak' : ''}`} />);
    }
    return arr;
  };

  return (
    <div className="top-bar">
      <div className="tb-group">
        <div className="tb-stack">
          <span className="tb-label">시스템 상태</span>
          <div className="sys-stats">
            <div className="stat"><span className="stat-name">CPU</span><span className="stat-val">55%</span></div>
            <div className="stat"><span className="stat-name">RAM</span><span className="stat-val">77%</span></div>
            <div className="stat"><span className="stat-name">GPU</span><span className="stat-val">N/A</span></div>
          </div>
        </div>
        {alertActive && <span className="badge-warn">감지 응답</span>}
      </div>

      <div className="tb-group">
        <div className="tb-stack">
          <span className="tb-label">현재시간</span>
          <div className="clock">{hh}:{mm}:{ss}</div>
        </div>
      </div>

      <div className="tb-group">
        <div className="tb-stack">
          <span className="tb-label">Embedded Audio</span>
          <div className="meter-group">
            <button className={`mute-btn ${muted ? 'active' : ''}`} onClick={() => setMuted(!muted)}>
              {muted ? '🔇' : '🔊'}
            </button>
            <div className="vol-slider"><div className="fill" style={{ width: '60%' }} /></div>
            <div className="meters">
              <div className="meter-col">{segs(muted ? 0 : meterL)}<div className="ch-label">L</div></div>
              <div className="meter-col">{segs(muted ? 0 : meterR)}<div className="ch-label">R</div></div>
            </div>
          </div>
        </div>
      </div>

      <div className="tb-group">
        <div className="tb-stack">
          <span className="tb-label">감지 현황</span>
          <div className="det-badges">
            <div className="det-badge"><span className="d-label">V</span><span className="d-val">3</span></div>
            <div className="det-badge"><span className="d-label">A</span><span className="d-val">2</span></div>
            <div className={`det-badge ${alertActive ? 'alert' : ''}`}><span className="d-label">EA</span><span className="d-val">1</span></div>
          </div>
        </div>
      </div>

      <div className="tb-actions">
        <button className={`act-btn ${detOn ? 'active' : ''}`} onClick={() => setDetOn(!detOn)}>
          <span className="main-label">감지 {detOn ? 'ON' : 'OFF'}</span>
          <span className="sub-label">{detOn ? '감시중' : '중지'}</span>
        </button>
        <button className={`act-btn ${showROI ? 'active' : ''}`} onClick={() => setShowROI(!showROI)}>
          <span className="main-label">영역 표시</span>
          <span className="sub-label">{showROI ? 'ON' : 'OFF'}</span>
        </button>
        <button className={`act-btn ${muted ? 'active' : ''}`} onClick={() => setMuted(!muted)}>
          <span className="main-label">Mute</span>
          <span className="sub-label">{muted ? 'ON' : 'OFF'}</span>
        </button>
        <button className={`act-btn ${alertActive && !ackPressed ? 'alert-on' : ''}`} onClick={() => setAckPressed(true)}>
          <span className="main-label">알림확인</span>
          <span className="sub-label">{alertActive && !ackPressed ? '확인필요' : '정상'}</span>
        </button>
        <button className="act-btn signoff-prep">
          <span className="main-label">그룹1 정파</span>
          <span className="sub-label">정파까지 {c1}</span>
        </button>
        <button className="act-btn signoff-idle">
          <span className="main-label">그룹2 정파</span>
          <span className="sub-label">정파준비까지 {c2}</span>
        </button>
        <button className="act-btn icon-only" onClick={openSettings} title="설정">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="12" cy="12" r="3"/>
            <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09a1.65 1.65 0 0 0-1-1.51 1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09a1.65 1.65 0 0 0 1.51-1 1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/>
          </svg>
        </button>
        <button className={`act-btn icon-only ${nightMode ? 'active' : ''}`} onClick={() => setNightMode(!nightMode)} title="야간모드">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>
          </svg>
        </button>
        <button className="act-btn icon-only" title="전체화면">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M8 3H5a2 2 0 0 0-2 2v3m18 0V5a2 2 0 0 0-2-2h-3m0 18h3a2 2 0 0 0 2-2v-3M3 16v3a2 2 0 0 0 2 2h3"/>
          </svg>
        </button>
      </div>
    </div>
  );
}

window.TopBar = TopBar;
