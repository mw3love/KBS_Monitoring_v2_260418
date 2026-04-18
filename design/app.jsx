// ================================================================
// App shell with 3 variations + Tweaks + Settings dialog
// ================================================================
const { useState: useStateA, useEffect: useEffectA } = React;

const TWEAK_DEFAULTS = /*EDITMODE-BEGIN*/{
  "density": "normal",
  "sketchy": false,
  "orangeHue": 32,
  "alertActive": true
}/*EDITMODE-END*/;

function VariantSwitcher({ variant, setVariant, view, setView }) {
  return (
    <div className="var-switcher">
      <button className={view === 'main' && variant === 1 ? 'active' : ''} onClick={() => { setView('main'); setVariant(1); }}>V1 표준</button>
      <button className={view === 'main' && variant === 2 ? 'active' : ''} onClick={() => { setView('main'); setVariant(2); }}>V2 오렌지 적극</button>
      <button className={view === 'main' && variant === 3 ? 'active' : ''} onClick={() => { setView('main'); setVariant(3); }}>V3 재구조</button>
      <div className="sep" />
      <button className={view === 'settings' ? 'active' : ''} onClick={() => setView('settings')}>⚙ 설정 7탭</button>
    </div>
  );
}

function TweaksPanel({ open, tweaks, setTweaks }) {
  if (!open) return null;
  const upd = (k, v) => {
    setTweaks(t => ({ ...t, [k]: v }));
    window.parent.postMessage({ type: '__edit_mode_set_keys', edits: { [k]: v } }, '*');
  };
  return (
    <div className="tweaks-panel open">
      <div className="tp-head">TWEAKS</div>
      <div className="tp-body">
        <div className="tp-row">
          <label>정보 밀도</label>
          <div style={{display: 'flex', gap: 4}}>
            {['compact', 'normal', 'spacious'].map(d => (
              <button key={d} onClick={() => upd('density', d)}
                className="btn-secondary"
                style={{flex: 1, padding: '4px 6px', fontSize: 10, borderColor: tweaks.density === d ? 'var(--orange)' : undefined, color: tweaks.density === d ? 'var(--orange)' : undefined}}>
                {d === 'compact' ? '압축' : d === 'normal' ? '보통' : '여유'}
              </button>
            ))}
          </div>
        </div>
        <div className="tp-row">
          <label>와이어프레임 충실도</label>
          <div style={{display: 'flex', gap: 4}}>
            <button onClick={() => upd('sketchy', false)} className="btn-secondary"
              style={{flex: 1, padding: '4px 6px', fontSize: 10, borderColor: !tweaks.sketchy ? 'var(--orange)' : undefined, color: !tweaks.sketchy ? 'var(--orange)' : undefined}}>Hi-fi</button>
            <button onClick={() => upd('sketchy', true)} className="btn-secondary"
              style={{flex: 1, padding: '4px 6px', fontSize: 10, borderColor: tweaks.sketchy ? 'var(--orange)' : undefined, color: tweaks.sketchy ? 'var(--orange)' : undefined}}>Sketch</button>
          </div>
        </div>
        <div className="tp-row">
          <label>오렌지 Hue <span className="val">{tweaks.orangeHue}°</span></label>
          <input type="range" min="0" max="60" value={tweaks.orangeHue} onChange={e => upd('orangeHue', Number(e.target.value))} />
        </div>
        <div className="tp-row">
          <label>알림 상태</label>
          <button onClick={() => upd('alertActive', !tweaks.alertActive)} className="btn-secondary"
            style={{padding: '4px 8px', fontSize: 11, borderColor: tweaks.alertActive ? 'var(--alert-red)' : undefined, color: tweaks.alertActive ? 'var(--alert-red)' : undefined}}>
            {tweaks.alertActive ? '● 알림 발생 중' : '○ 정상'}
          </button>
        </div>
      </div>
    </div>
  );
}

function MainWindow({ variant, alertActive }) {
  const [muted, setMuted] = useStateA(false);
  const [detOn, setDetOn] = useStateA(true);
  const [showROI, setShowROI] = useStateA(true);
  const [ackPressed, setAckPressed] = useStateA(false);
  const [nightMode, setNightMode] = useStateA(true);

  useEffectA(() => { setAckPressed(false); }, [alertActive]);

  const variantCls = `v${variant}`;

  return (
    <div className={`app-chrome ${variantCls}`}>
      <div className="title-bar">
        <span className="brand-dot" />
        <span className="app-name">KBS Monitoring</span>
        <span className="app-ver">v2.0.1</span>
        <span className="mode-ind">LAYOUT <span className="v">V{variant}</span> · {nightMode ? '야간모드' : '주간모드'} · {detOn ? '감시중' : '중지'}</span>
        <div className="win-ctrl"><span>—</span><span>□</span><span>✕</span></div>
      </div>
      <TopBar
        alertActive={alertActive}
        muted={muted} setMuted={setMuted}
        detOn={detOn} setDetOn={setDetOn}
        showROI={showROI} setShowROI={setShowROI}
        ackPressed={ackPressed} setAckPressed={setAckPressed}
        nightMode={nightMode} setNightMode={setNightMode}
        variant={variant}
      />
      <div className="main-layout" style={variant === 3 ? { gridTemplateColumns: '280px 1fr 340px' } : {}}>
        {variant === 3 && <LeftRail />}
        <VideoArea showROI={showROI} alertActive={alertActive} variant={variant} />
        <LogPanel alertActive={alertActive} />
      </div>
    </div>
  );
}

function App() {
  const [view, setView] = useStateA('main');
  const [variant, setVariant] = useStateA(() => Number(localStorage.getItem('kbs-variant')) || 1);
  const [tweaksOpen, setTweaksOpen] = useStateA(false);
  const [tweaks, setTweaks] = useStateA(TWEAK_DEFAULTS);

  useEffectA(() => {
    localStorage.setItem('kbs-variant', String(variant));
  }, [variant]);

  // Apply tweaks to body
  useEffectA(() => {
    document.body.classList.toggle('compact', tweaks.density === 'compact');
    document.body.classList.toggle('spacious', tweaks.density === 'spacious');
    document.body.classList.toggle('sketchy', tweaks.sketchy);
    // Re-derive orange via hue
    const lch = `oklch(0.71 0.12 ${tweaks.orangeHue})`;
    document.documentElement.style.setProperty('--orange', lch);
    document.documentElement.style.setProperty('--orange-soft', `oklch(0.78 0.1 ${tweaks.orangeHue})`);
    document.documentElement.style.setProperty('--orange-deep', `oklch(0.58 0.12 ${tweaks.orangeHue})`);
  }, [tweaks]);

  // Tweak mode protocol
  useEffectA(() => {
    const handler = (e) => {
      if (e.data?.type === '__activate_edit_mode') setTweaksOpen(true);
      if (e.data?.type === '__deactivate_edit_mode') setTweaksOpen(false);
    };
    window.addEventListener('message', handler);
    window.parent.postMessage({ type: '__edit_mode_available' }, '*');
    return () => window.removeEventListener('message', handler);
  }, []);

  return (
    <>
      <VariantSwitcher variant={variant} setVariant={setVariant} view={view} setView={setView} />
      {view === 'main' && <MainWindow variant={variant} alertActive={tweaks.alertActive} />}
      {view === 'settings' && <SettingsDialog onClose={() => setView('main')} />}
      <TweaksPanel open={tweaksOpen} tweaks={tweaks} setTweaks={setTweaks} />
    </>
  );
}

const root = ReactDOM.createRoot(document.getElementById('root'));
root.render(<App />);
