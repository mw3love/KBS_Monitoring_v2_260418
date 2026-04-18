// ================================================================
// Settings Dialog — 7 tabs
// ================================================================
const { useState: useStateS } = React;

const SETTINGS_TABS = [
  { id: 'video', label: '영상설정' },
  { id: 'video-area', label: '비디오 영역 설정' },
  { id: 'audio-area', label: '오디오 레벨미터 영역 설정' },
  { id: 'sensitivity', label: '감도설정' },
  { id: 'signoff', label: '정파설정' },
  { id: 'alert', label: '알림설정' },
  { id: 'save', label: '저장/불러오기' }
];

function SettingsDialog({ onClose }) {
  const [tab, setTab] = useStateS('sensitivity');

  return (
    <div className="settings-shell">
      <div className="title-bar">
        <span className="brand-dot" />
        <span className="app-name">설정</span>
        <span className="app-ver">SETTINGS</span>
        <div className="win-ctrl">
          <span onClick={onClose} style={{ cursor: 'pointer' }}>— □ ✕</span>
        </div>
      </div>
      <div className="settings-tabs">
        {SETTINGS_TABS.map((t, i) => (
          <button key={t.id} className={`settings-tab ${tab === t.id ? 'active' : ''}`} onClick={() => setTab(t.id)}>
            {t.label}
          </button>
        ))}
      </div>
      <div className="settings-body">
        {tab === 'video' && <TabVideo />}
        {tab === 'video-area' && <TabArea kind="video" />}
        {tab === 'audio-area' && <TabArea kind="audio" />}
        {tab === 'sensitivity' && <TabSensitivity />}
        {tab === 'signoff' && <TabSignoff />}
        {tab === 'alert' && <TabAlert />}
        {tab === 'save' && <TabSave />}
      </div>
    </div>
  );
}

// --- Tab: Video input
function TabVideo() {
  return (
    <>
      <div className="settings-section">
        <div className="settings-section-head"><span className="dot" />입력 소스</div>
        <div className="settings-section-body">
          <div className="settings-row">
            <label>포트 번호</label>
            <input className="input-dark" defaultValue="1" />
            <span className="desc">입력 포트 (1~4)</span>
          </div>
          <div className="settings-row">
            <label>비상 입력 (테스트용)</label>
            <input className="input-dark" placeholder="파일 선택 안 함 — 포트 사용" style={{gridColumn: '2 / 3'}} />
            <div style={{display: 'flex', gap: 6}}>
              <button className="btn-secondary">찾아보기</button>
              <button className="btn-secondary">초기화</button>
            </div>
          </div>
          <div className="settings-row">
            <label style={{gridColumn: '1 / -1', fontSize: 11, color: 'var(--text-2)', marginTop: 4}}>
              <span style={{color: 'var(--orange)'}}>※</span> MP4 등 영상 파일을 실제로 포트 대신 소스로 사용합니다. 파일을 선택하면 재생 자동으로 진행되며, 정지나 다시 시작도 지원합니다.
            </label>
          </div>
        </div>
      </div>

      <div className="settings-section">
        <div className="settings-section-head"><span className="dot" />자동 녹화 설정</div>
        <div className="settings-section-body">
          <div className="settings-row">
            <label><input type="checkbox" className="chk" defaultChecked /> 알림 발생 시 자동 녹화 활성화</label>
            <span />
            <span className="desc">알림 발생 직전부터 직후까지 자동 저장</span>
          </div>
          <div className="settings-row">
            <label>저장 폴더</label>
            <input className="input-dark" defaultValue="recordings" style={{gridColumn: '2 / 3'}} />
            <div style={{display: 'flex', gap: 6}}>
              <button className="btn-secondary">찾아보기</button>
              <button className="btn-secondary">폴더 열기</button>
            </div>
          </div>
          <div className="settings-row">
            <label>시작 전 버퍼(초)</label>
            <input className="input-dark" defaultValue="5" />
            <span className="desc">1~30 / 기본값 <span className="hi">5</span></span>
          </div>
          <div className="settings-row">
            <label>시간 후 기록(초)</label>
            <input className="input-dark" defaultValue="15" />
            <span className="desc">1~60 / 기본값 <span className="hi">15</span></span>
          </div>
          <div className="settings-row">
            <label>최대 보관 기간(일)</label>
            <input className="input-dark" defaultValue="7" />
            <span className="desc">1~365 / 보관 기간 초과 파일은 자동 삭제</span>
          </div>
        </div>
      </div>

      <div className="settings-section">
        <div className="settings-section-head"><span className="dot" />녹화 품질 설정</div>
        <div className="settings-section-body">
          <div className="settings-row">
            <label>출력 해상도</label>
            <select className="select-dark"><option>960×540 (기본값)</option><option>1280×720</option><option>1920×1080</option></select>
            <span className="desc">저해상도일수록 파일 크기 절약</span>
          </div>
          <div className="settings-row">
            <label>출력 FPS</label>
            <select className="select-dark"><option>30 fps</option><option>25 fps</option><option>15 fps</option></select>
            <span className="desc">실시간과 맞춰 기록</span>
          </div>
        </div>
      </div>

      <div style={{padding: 10, background: 'var(--bg-0)', border: '1px dashed var(--border-strong)', fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-2)'}}>
        출력 해상도: <span style={{color: 'var(--orange)'}}>960×540</span> | FPS: <span style={{color: 'var(--orange)'}}>30</span> | 버퍼 메모리: 약 <span style={{color: 'var(--orange)'}}>27.8 MB</span> | 녹화 파일 크기: 약 <span style={{color: 'var(--orange)'}}>41~77 MB</span> / 20초 | 코덱: <span style={{color: 'var(--orange)'}}>mp4v</span>
      </div>

      <div style={{marginTop: 16, display: 'flex', justifyContent: 'center'}}>
        <button className="btn-primary" style={{width: '100%'}}>영상설정 전체 초기화</button>
      </div>
    </>
  );
}

// --- Tab: Video/Audio area editor
function TabArea({ kind }) {
  return (
    <>
      <button className="btn-primary" style={{background: 'var(--ok-green)', color: 'white', marginBottom: 12}}>
        ▶ {kind === 'video' ? '비디오' : '오디오'} 감지영역 편집
      </button>
      <div style={{padding: 12, background: 'var(--bg-0)', border: '1px solid var(--border)', fontSize: 11, color: 'var(--text-1)', fontFamily: 'var(--font-mono)', lineHeight: 1.7, marginBottom: 16}}>
        <div style={{color: 'var(--orange)', marginBottom: 6}}>단축키:</div>
        <div>· Drag — 선택 영역 10px 이동</div>
        <div>· Shift + L — 선택 항목 1px 이동</div>
        <div>· Ctrl + ↑↓ — 선택 항목 크기 10px 조정</div>
        <div style={{color: 'var(--orange)', marginTop: 8, marginBottom: 6}}>마우스사용:</div>
        <div>· 빈 곳 드래그 — 새 영역</div>
        <div>· 영역 프레그 — 이동</div>
        <div>· Shift + 프레그 — 스팀/수플룸값바꾸기</div>
        <div>· Ctrl + 드래그(번 위) — 복사 대상 선택</div>
        <div>· Ctrl+휠(위) — 영역 돋보기/돋보기</div>
      </div>
      <div style={{fontSize: 12, color: 'var(--text-0)', fontWeight: 600, marginBottom: 8}}>감지영역 List</div>
      <table style={{width: '100%', borderCollapse: 'collapse', fontSize: 11, fontFamily: 'var(--font-mono)'}}>
        <thead>
          <tr style={{background: 'var(--bg-2)', borderBottom: '1px solid var(--border)'}}>
            <th style={{padding: '6px 10px', textAlign: 'left', width: 60}}>라벨</th>
            <th style={{padding: '6px 10px', textAlign: 'left'}}>매체명</th>
            <th style={{padding: '6px 10px', textAlign: 'left', width: 60}}>X</th>
            <th style={{padding: '6px 10px', textAlign: 'left', width: 60}}>Y</th>
            <th style={{padding: '6px 10px', textAlign: 'left', width: 60}}>W</th>
            <th style={{padding: '6px 10px', textAlign: 'left', width: 60}}>H</th>
          </tr>
        </thead>
        <tbody>
          {kind === 'video' ? (
            <>
              <tr style={{borderBottom: '1px solid var(--border)'}}><td style={{padding: 6}}>V1</td><td style={{padding: 6}}>1TV</td><td style={{padding: 6}}>192</td><td style={{padding: 6}}>162</td><td style={{padding: 6}}>538</td><td style={{padding: 6}}>432</td></tr>
              <tr style={{borderBottom: '1px solid var(--border)'}}><td style={{padding: 6}}>V2</td><td style={{padding: 6}}>2TV</td><td style={{padding: 6}}>1152</td><td style={{padding: 6}}>216</td><td style={{padding: 6}}>422</td><td style={{padding: 6}}>324</td></tr>
              <tr style={{borderBottom: '1px solid var(--border)', background: 'var(--orange-tint)'}}><td style={{padding: 6, color: 'var(--orange)'}}>V3</td><td style={{padding: 6, color: 'var(--orange)'}}>EBS</td><td style={{padding: 6}}>384</td><td style={{padding: 6}}>756</td><td style={{padding: 6}}>346</td><td style={{padding: 6}}>216</td></tr>
            </>
          ) : (
            <>
              <tr style={{borderBottom: '1px solid var(--border)'}}><td style={{padding: 6}}>A1</td><td style={{padding: 6}}>1TV</td><td style={{padding: 6}}>345</td><td style={{padding: 6}}>864</td><td style={{padding: 6}}>230</td><td style={{padding: 6}}>216</td></tr>
              <tr style={{borderBottom: '1px solid var(--border)'}}><td style={{padding: 6}}>A2</td><td style={{padding: 6}}>2TV</td><td style={{padding: 6}}>1420</td><td style={{padding: 6}}>756</td><td style={{padding: 6}}>168</td><td style={{padding: 6}}>216</td></tr>
            </>
          )}
        </tbody>
      </table>
      <div style={{display: 'flex', gap: 6, marginTop: 12}}>
        <button className="btn-secondary">추가</button>
        <button className="btn-secondary">삭제</button>
        <button className="btn-secondary">▲ 위로</button>
        <button className="btn-secondary">▼ 아래로</button>
        <button className="btn-secondary" style={{marginLeft: 'auto'}}>전체 지우기</button>
      </div>
    </>
  );
}

// --- Tab: Sensitivity
function NumRow({ label, defaultValue, unit, desc, hiVal }) {
  return (
    <div className="settings-row">
      <label>{label}</label>
      <div style={{display: 'flex', alignItems: 'center', gap: 8}}>
        <input className="input-dark" defaultValue={defaultValue} />
        {unit && <span style={{fontSize: 11, color: 'var(--text-2)', whiteSpace: 'nowrap'}}>{unit}</span>}
      </div>
      <span className="desc">{desc} {hiVal && <span className="hi">{hiVal}</span>}</span>
    </div>
  );
}

function HSVRow({ label, type, min, max, desc }) {
  return (
    <div className="settings-row">
      <label>{label}</label>
      <div className="range-wrap">
        <div className={`range-track ${type}`}>
          <div className="range-handle" style={{ left: `${min}%` }} />
          <div className="range-handle" style={{ left: `${max}%` }} />
        </div>
      </div>
      <span className="desc">{desc}</span>
    </div>
  );
}

function TabSensitivity() {
  return (
    <>
      <div className="settings-section">
        <div className="settings-section-head"><span className="dot" />블랙 감지</div>
        <div className="settings-section-body">
          <NumRow label="밝기 임계값" defaultValue="5" desc="0~255 / 감지 픽셀률 이 어디까지 어두운지 기준" hiVal="(기본값 5)" />
          <NumRow label="어두운 픽셀 비율 임계값(%)" defaultValue="98.0" desc="50~100% / 임계값이 비율 이상 어두운면 블랙으로 판단" hiVal="(기본값 98)" />
          <NumRow label="모션 억제 비율" defaultValue="0.2" desc="0.0~5.0 / 화면에 움직임(change)이 이 비율 이상이면 블랙 억제" hiVal="(기본값 0.2)" />
          <NumRow label="몇 초 이상시 알람 발생(초)" defaultValue="20" desc="1~120 / 얼마나 이 시간 지속되어야 알람 발생" hiVal="(기본값 20)" />
          <NumRow label="알람 지속시간(초)" defaultValue="60" desc="1~60 / 알람 발생 시 소리를 출력함 시간" hiVal="(기본값 60)" />
        </div>
      </div>

      <div className="settings-section">
        <div className="settings-section-head"><span className="dot" />스틸 감지</div>
        <div className="settings-section-body">
          <NumRow label="픽셀 단위 민감도" defaultValue="4" desc="0~255 / 각 픽셀이 얼마 차이나 이 이상일때 변화로 기록" hiVal="(기본값 4)" />
          <NumRow label="픽셀 변화량 한계값(%)" defaultValue="10.0" desc="1.0~50.0% / 아무른 장수 이 비율이 넘어야 이 비율 이상 변한다면 스틸 아님" hiVal="(기본값 10%)" />
          <NumRow label="다이나믹 리셋 프레임 수" defaultValue="3" desc="1~10개까지 / 이 프레임 간 차례 속에 정상유지가 이 간 프레임이면 스틸 해제" hiVal="(기본값 3)" />
          <NumRow label="몇 초 이상시 알람 발생(초)" defaultValue="60" desc="1~120초 / 스틸이 이 시간 이상 지속되면 알람 발생" hiVal="(기본값 60)" />
          <NumRow label="알람 지속시간(초)" defaultValue="60" desc="1~60초 / 알람 발생 시 소리를 출력함 시간" hiVal="(기본값 60)" />
        </div>
      </div>

      <div className="settings-section">
        <div className="settings-section-head"><span className="dot" />오디오 레벨미터 감지 (HSV)</div>
        <div className="settings-section-body">
          <HSVRow label="H 범위 (색조)" type="hue" min={30} max={60} desc="0~179 / OpenCV HSV 범위 (기본값 40~95 = 소블 계열)" />
          <HSVRow label="S 범위 (채도)" type="sat" min={30} max={90} desc="0~255 / 채도 범위 (기본값 50~255)" />
          <HSVRow label="V 범위 (명도)" type="val" min={20} max={90} desc="0~255 / 명도 범위 (기본값 60~255)" />
          <NumRow label="감지 픽셀 비율(%)" defaultValue="5" desc="1~50% / ROI 내 HSV 범위 색상 픽셀이 이 값 이상이면 활성 (기본값 5%)" />
          <NumRow label="몇 초 이상시 알람 발생(초)" defaultValue="20" desc="1~120초 / 레벨미터 비활성이 이 시간 이상 지속되면 알람 (기본값 20초)" />
          <NumRow label="알람 지속시간(초)" defaultValue="60" desc="1~60초 / 알람 발생 시 소리를 출력함 시간 (기본값 60초)" />
          <NumRow label="복구 민테이프(초)" defaultValue="2" desc="0~10초 / 알람 발생 후 정상 추주된 이후 레벨 지속 시간 (기본값 2초, 0=즉시복구)" />
        </div>
      </div>

      <div className="settings-section">
        <div className="settings-section-head"><span className="dot" />임베디드 오디오 감지 (무음 감지)</div>
        <div className="settings-section-body">
          <NumRow label="무음 임계값(dB)" defaultValue="-50" desc="-60~0 / 이 값 이하일 때 무음으로 판단 (기본값 -50dB)" />
          <NumRow label="몇 초 이상시 알람 발생(초)" defaultValue="20" desc="1~120초 / 무음이 이 시간 이상 지속되면 알람 발생 (기본값 20초)" />
          <NumRow label="알람 지속시간(초)" defaultValue="60" desc="1~60초 / 알람 발생 시 소리를 출력함 시간 (기본값 60초)" />
        </div>
      </div>

      <div className="settings-section">
        <div className="settings-section-head"><span className="dot" />성능 설정</div>
        <div className="settings-section-body">
          <div className="settings-row">
            <label>감지 주기</label>
            <select className="select-dark"><option>100ms</option><option selected>200ms</option><option>500ms</option></select>
            <span className="desc">감지 반응 민감도 (속도 늘 수록 CPU 사용 점수; 10초 감지의 기본 500ms까지 한다)</span>
          </div>
          <div className="settings-row">
            <label>감지 해상도</label>
            <select className="select-dark"><option selected>원본 (1920×1080)</option><option>0.5× 해상도 (960×540)</option><option>0.25× 해상도 (480×270)</option></select>
            <span className="desc">50% 시 CPU 부담 50% 절감 — 감지 정확도 약간 감소</span>
          </div>
          <div className="settings-row">
            <label>블랙 감지</label>
            <label><input type="checkbox" className="chk" defaultChecked /> 블랙 감지 활성화</label>
            <span className="desc">비활성화 시 블랙 감시 해제</span>
          </div>
          <div className="settings-row">
            <label>스틸 감지</label>
            <label><input type="checkbox" className="chk" defaultChecked /> 정지 영상 감지 활성화</label>
            <span className="desc">비활성화 시 스틸로 해제</span>
          </div>
          <div className="settings-row">
            <label>오디오 레벨미터 검사</label>
            <label><input type="checkbox" className="chk" defaultChecked /> HSV 색상 감지 활성화</label>
            <span className="desc">비활성화 시 HSV 모니터링 해제 — 기능 보호위해 추천 없음</span>
          </div>
          <div className="settings-row">
            <label>임베디드 오디오</label>
            <label><input type="checkbox" className="chk" defaultChecked /> 임베디드 오디오 감지 활성화</label>
            <span className="desc">비활성화 시 무음 감지 연산 안함</span>
          </div>
          <div style={{display: 'flex', gap: 8, marginTop: 12}}>
            <button className="btn-primary">자동 성능 감지</button>
            <button className="btn-secondary">성능 설정 안내</button>
          </div>
        </div>
      </div>
    </>
  );
}

// --- Tab: Signoff
function TabSignoff() {
  return (
    <>
      <div className="settings-section">
        <div className="settings-section-head"><span className="dot" />자동 정파 설정</div>
        <div className="settings-section-body">
          <div className="settings-row">
            <label><input type="checkbox" className="chk" defaultChecked /> 자동정파 동일화</label>
            <span />
            <button className="btn-secondary">자동정파 안내</button>
          </div>
        </div>
      </div>

      {[1, 2].map(g => (
        <div key={g} className="settings-section">
          <div className="settings-section-head"><span className="dot" />Group {g}</div>
          <div className="settings-section-body">
            <div className="settings-row">
              <label>그룹명</label>
              <input className="input-dark" defaultValue={g === 1 ? '1TV' : '2TV'} />
              <span className="desc">그룹 식별자</span>
            </div>
            <div className="settings-row">
              <label>정파모드 시작</label>
              <div style={{display: 'flex', gap: 4, alignItems: 'center'}}>
                <input className="input-dark" defaultValue={g === 1 ? '03' : '02'} style={{width: 50}} /> :
                <input className="input-dark" defaultValue={g === 1 ? '30' : '00'} style={{width: 50}} />
                <span style={{color: 'var(--text-2)', marginLeft: 6}}>종료:</span>
                <input className="input-dark" defaultValue="05" style={{width: 50}} /> :
                <input className="input-dark" defaultValue="00" style={{width: 50}} />
                <label style={{marginLeft: 8}}><input type="checkbox" className="chk" /> 익일</label>
              </div>
              <span />
            </div>
            <div className="settings-row">
              <label>몇 분전 정파준비 활성화</label>
              <select className="select-dark"><option>3시간 전</option><option>1시간 전</option><option>30분 전</option></select>
              <span className="desc">00:30에 정파준비 시작</span>
            </div>
            <div className="settings-row">
              <label>몇 분전 정파해제준비 활성화</label>
              <select className="select-dark"><option>3시간 전</option><option>30분 전</option></select>
              <span className="desc">02:00에 정파해제준비 시작</span>
            </div>
            <div className="settings-row">
              <label>몇 초 이상시 정파해제</label>
              <input className="input-dark" defaultValue="5초 (기본)" />
              <span className="desc">정파모드 조기 해제 임계</span>
            </div>
            <div className="settings-row">
              <label>요일</label>
              <div style={{display: 'flex', gap: 4, flexWrap: 'wrap'}}>
                <label>매일</label>
                {['월', '화', '수', '목', '금', '토', '일'].map(d => (
                  <label key={d} style={{display: 'flex', gap: 2, alignItems: 'center', fontSize: 11}}>
                    <input type="checkbox" className="chk" defaultChecked={g === 1 || d !== '일'} /> {d}
                  </label>
                ))}
              </div>
              <span className="desc" style={{fontSize: 10}}>(정파준비 시작 시간이 이 속 날의 요일 기준; 조기가 전날 밤이면 전날 요일 선택)</span>
            </div>
            <div className="settings-row">
              <label>정파 감지영역</label>
              <button className="btn-secondary">감지영역 선택</button>
              <span style={{color: 'var(--alert-red)'}}>선택 없음</span>
            </div>
          </div>
        </div>
      ))}

      <div className="settings-section">
        <div className="settings-section-head"><span className="dot" />정파 알림음</div>
        <div className="settings-section-body">
          {['정파준비 시작:', '정파모드 진입:', '정파 해제:'].map(lbl => (
            <div className="settings-row" key={lbl}>
              <label>{lbl}</label>
              <input className="input-dark" defaultValue="resources/sounds/sign_off.wav" style={{gridColumn: '2 / 3'}} />
              <div style={{display: 'flex', gap: 6}}>
                <button className="btn-secondary">파일 선택</button>
                <button className="btn-secondary">테스트</button>
              </div>
            </div>
          ))}
        </div>
      </div>

      <button className="btn-primary" style={{width: '100%', marginTop: 12}}>정파설정 전체 초기화</button>
    </>
  );
}

// --- Tab: Alert
function TabAlert() {
  return (
    <>
      <div className="settings-section">
        <div className="settings-section-head"><span className="dot" />알림음 공통 설정</div>
        <div className="settings-section-body">
          <div className="settings-row">
            <label>알림음 파일</label>
            <input className="input-dark" defaultValue="resources/sounds/alarm.wav" style={{gridColumn: '2 / 3'}} />
            <div style={{display: 'flex', gap: 6}}>
              <button className="btn-secondary">찾아보기</button>
              <button className="btn-secondary">초기화</button>
              <button className="btn-secondary">테스트</button>
            </div>
          </div>
        </div>
      </div>

      <div className="settings-section">
        <div className="settings-section-head"><span className="dot" />텔레그램 봇 설정</div>
        <div className="settings-section-body">
          <div className="settings-row">
            <label><input type="checkbox" className="chk" /> 텔레그램 알림 활성화</label>
            <span />
            <span className="desc">@BotFather에서 발급받은 토큰</span>
          </div>
          <div className="settings-row">
            <label>Bot Token</label>
            <input className="input-dark" placeholder="텔레그램 BotFather에서 발급받은 토큰" style={{gridColumn: '2 / 4'}} />
          </div>
          <div className="settings-row">
            <label>Chat ID</label>
            <input className="input-dark" placeholder="수신할 채팅/그룹/채널 ID" style={{gridColumn: '2 / 4'}} />
          </div>
          <button className="btn-secondary" style={{marginTop: 8}}>연결 테스트</button>
        </div>
      </div>

      <div className="settings-section">
        <div className="settings-section-head"><span className="dot" />텔레그램 알림 옵션</div>
        <div className="settings-section-body">
          {[
            '알림 발생 시 스냅샷 이미지 첨부',
            '블랙 감지 알림',
            '스틸 감지 알림',
            '오디오 레벨미터 감지 알림',
            '임베디드 오디오 감지 알림'
          ].map(x => (
            <div className="settings-row" key={x}>
              <label><input type="checkbox" className="chk" defaultChecked /> {x}</label>
              <span />
              <span />
            </div>
          ))}
          <div className="settings-row">
            <label>재전송 대기(초)</label>
            <input className="input-dark" defaultValue="60" />
            <span className="desc">동일 감지유형 내 연속 재전송 방지</span>
          </div>
        </div>
      </div>

      <div className="settings-section">
        <div className="settings-section-head"><span className="dot" />자동 재시작</div>
        <div className="settings-section-body">
          <div className="settings-row">
            <label><input type="checkbox" className="chk" /> 재시작 시각 1</label>
            <div style={{display: 'flex', gap: 4}}>
              <input className="input-dark" defaultValue="21" style={{width: 60}} /> :
              <input className="input-dark" defaultValue="66" style={{width: 60}} />
            </div>
            <span />
          </div>
          <div className="settings-row">
            <label><input type="checkbox" className="chk" /> 재시작 시각 2</label>
            <div style={{display: 'flex', gap: 4}}>
              <input className="input-dark" defaultValue="15" style={{width: 60}} /> :
              <input className="input-dark" defaultValue="00" style={{width: 60}} />
            </div>
            <span />
          </div>
          <div style={{fontSize: 11, color: 'var(--text-2)', marginTop: 6}}>
            고유스스가 설정시 시각이 되면 OS 리소스(DB, 메모리 등)를 초기화합니다.
          </div>
        </div>
      </div>
    </>
  );
}

// --- Tab: Save / Load
function TabSave() {
  return (
    <>
      <div className="settings-section">
        <div className="settings-section-head"><span className="dot" />설정 파일 저장</div>
        <div className="settings-section-body" style={{padding: 0}}>
          <button className="btn-primary" style={{width: '100%', padding: '18px', background: 'transparent', color: 'var(--orange)', border: '1px dashed var(--orange)'}}>
            현재 설정 저장...
          </button>
        </div>
      </div>

      <div className="settings-section">
        <div className="settings-section-head"><span className="dot" />설정 파일 불러오기</div>
        <div className="settings-section-body" style={{padding: 0}}>
          <button className="btn-primary" style={{width: '100%', padding: '18px', background: 'transparent', color: 'var(--orange)', border: '1px dashed var(--orange)'}}>
            설정 파일 불러오기...
          </button>
        </div>
      </div>

      <div className="settings-section">
        <div className="settings-section-head"><span className="dot" />기본값으로 초기화</div>
        <div className="settings-section-body" style={{padding: 0}}>
          <button className="btn-primary" style={{width: '100%', padding: '18px', background: 'transparent', color: 'var(--alert-red)', border: '1px dashed var(--alert-red)'}}>
            기본값으로 초기화
          </button>
        </div>
      </div>

      <div className="settings-section">
        <div className="settings-section-head"><span className="dot" />About</div>
        <div className="settings-section-body" style={{fontFamily: 'var(--font-mono)', fontSize: 12, lineHeight: 1.8}}>
          <div><span style={{color: 'var(--text-2)'}}>Version:</span> <span style={{color: 'var(--orange)'}}>KBS Monitoring v2.0.1</span></div>
          <div><span style={{color: 'var(--text-2)'}}>Date:</span> 2026-04-18</div>
          <div><span style={{color: 'var(--text-2)'}}>GitHub:</span> <a href="#" style={{color: 'var(--orange-soft)'}}>github.com/kbs/monitoring-v2</a></div>
          <div><span style={{color: 'var(--text-2)'}}>E-mail:</span> <a href="#" style={{color: 'var(--orange-soft)'}}>monitoring@kbs.co.kr</a></div>
        </div>
      </div>

      <h3 style={{color: 'var(--text-0)', marginTop: 24, fontSize: 13}}>정파 버튼 상태 미리보기</h3>
      <div className="signoff-states-demo">
        <div>
          <button className="act-btn signoff-idle" style={{width: 140, height: 56}}>
            <span className="main-label">그룹1 정파</span>
            <span className="sub-label">정파준비까지 1D [06:06:26]</span>
          </button>
          <div className="signoff-demo-label">IDLE</div>
        </div>
        <div>
          <button className="act-btn signoff-prep" style={{width: 140, height: 56}}>
            <span className="main-label">그룹1 정파준비</span>
            <span className="sub-label">정파까지 [02:14:33]</span>
          </button>
          <div className="signoff-demo-label">PREPARATION</div>
        </div>
        <div>
          <button className="act-btn signoff-active" style={{width: 140, height: 56}}>
            <span className="main-label">그룹1 정파중</span>
            <span className="sub-label">정파해제준비까지 [00:45:12]</span>
          </button>
          <div className="signoff-demo-label">SIGNOFF</div>
        </div>
      </div>
    </>
  );
}

window.SettingsDialog = SettingsDialog;
