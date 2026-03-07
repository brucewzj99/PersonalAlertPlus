import React, { useState, useEffect } from 'react';
import './index.css';

interface Alert {
  id: string;
  senior_id: string;
  risk_level: 'URGENT' | 'NON_URGENT' | 'UNCERTAIN' | 'FALSE_ALARM';
  risk_score: number;
  transcription?: string;
  audio_url?: string;
  created_at: string;
  ambulance_dispatched?: boolean;
  family_called?: boolean;
  is_attended?: boolean;
  is_resolved?: boolean;
  seniors?: {
    full_name: string;
    phone_number?: string;
    address?: string;
  };
}

const App: React.FC = () => {
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [selectedCase, setSelectedCase] = useState<Alert | null>(null);
  const [newSeverity, setNewSeverity] = useState('');
  const [saveAsExample, setSaveAsExample] = useState(false);

  useEffect(() => {
    fetchAlerts();
    const interval = setInterval(fetchAlerts, 5000); 
    return () => clearInterval(interval);
  }, []);

  const fetchAlerts = async () => {
    try {
      const response = await fetch('/api/v1/operator/alerts');
      if (!response.ok) throw new Error('Network response was not ok');
      const data = await response.json();
      
      if (!Array.isArray(data)) {
        console.error('Expected array of alerts, got:', data);
        return;
      }

      if (data.length === 0) {
        setAlerts([
          {
            id: 'demo-1',
            senior_id: 's1',
            risk_level: 'URGENT',
            risk_score: 0.98,
            transcription: 'Help me, I fell down in the kitchen and I cannot get up! My leg is hurting very bad.',
            audio_url: 'https://www.soundhelix.com/examples/mp3/SoundHelix-Song-1.mp3',
            created_at: new Date().toISOString(),
            ambulance_dispatched: false,
            family_called: false,
            is_attended: true,
            seniors: { full_name: 'Tan Ah Kow', phone_number: '9876 5432', address: 'Blk 11 Jia De Street, #01-01' }
          },
          {
            id: 'demo-2',
            senior_id: 's2',
            risk_level: 'UNCERTAIN',
            risk_score: 0.45,
            transcription: 'I hear some loud crashing sounds coming from the bedroom. Please check.',
            created_at: new Date(Date.now() - 300000).toISOString(),
            ambulance_dispatched: false,
            family_called: false,
            is_attended: false,
            seniors: { full_name: 'Mdm Wong', phone_number: '9123 4455', address: 'Blk 12 Simei Ave, #10-120' }
          }
        ]);
      } else {
        setAlerts(data);
      }
    } catch (error) {
      console.error('Failed to fetch alerts:', error);
    }
  };

  const updateAlertInDB = async (alertId: string, updates: any) => {
    try {
      await fetch(`/api/v1/operator/alerts/${alertId}/override?save_as_example=${saveAsExample}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(updates)
      });
      fetchAlerts();
    } catch (error) {
      alert('Action failed. Please try again.');
    }
  };

  const handleSave = async () => {
    if (!selectedCase) return;
    const updates: any = {};
    
    // Auto-attend if not already
    updates.is_attended = true;

    if (newSeverity !== selectedCase.risk_level) {
        updates.risk_level = newSeverity;
    }

    await updateAlertInDB(selectedCase.id, updates);
    setSelectedCase(null);
  };

  const handleIntervention = async (type: 'ambulance' | 'family' | 'attend') => {
    if (!selectedCase) return;
    const updates: any = {};
    if (type === 'ambulance') updates.ambulance_dispatched = !selectedCase.ambulance_dispatched;
    if (type === 'family') updates.family_called = !selectedCase.family_called;
    
    // Manual attend is removed as per user request (operator shouldn't change it himself)
    if (type === 'attend') return; 

    const updatedCase = { ...selectedCase, ...updates };
    setSelectedCase(updatedCase);
    await updateAlertInDB(selectedCase.id, updates);
  };

  // Sorting: HANDLED (Urgent only, actions + saved) -> BOTTOM. Others -> TOP.
  const triageSort = (a: Alert, b: Alert) => {
    const isAHandled = a.risk_level === 'URGENT' && a.is_attended && a.ambulance_dispatched && a.family_called;
    const isBHandled = b.risk_level === 'URGENT' && b.is_attended && b.ambulance_dispatched && b.family_called;

    if (isAHandled !== isBHandled) return isAHandled ? 1 : -1;
    
    // Secondary sort: By time
    return new Date(b.created_at).getTime() - new Date(a.created_at).getTime();
  };

  const sortedAlerts = [...alerts].sort(triageSort);
  const urgent = sortedAlerts.filter(a => a.risk_level === 'URGENT');
  const nonUrgent = sortedAlerts.filter(a => a.risk_level === 'NON_URGENT');
  const uncertain = sortedAlerts.filter(a => a.risk_level === 'UNCERTAIN');
  const falseAlarm = sortedAlerts.filter(a => a.risk_level === 'FALSE_ALARM');

  const CaseListItem = ({ alert }: { alert: Alert }) => {
    // Only Urgent cases show "Handled" (grey-out)
    const isHandled = alert.risk_level === 'URGENT' && alert.is_attended && alert.ambulance_dispatched && alert.family_called;
    
    return (
      <div 
        className={`case-item ${isHandled ? 'handled-item' : ''}`}
        onClick={() => {
          setSelectedCase(alert);
          setNewSeverity(alert.risk_level);
          setSaveAsExample(false);
        }}
      >
        <div className="case-item-header">
          <span style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              {alert.seniors?.full_name || 'Unknown Senior'}
              {isHandled && <span style={{ fontSize: '0.6rem', background: '#334155', color: '#94a3b8', padding: '1px 5px', borderRadius: '4px', fontWeight: 700 }}>HANDLED</span>}
          </span>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <span className={`severity-badge badge-${(alert.risk_level || 'UNKNOWN').toLowerCase().replace('_', '-')}`} style={{ fontSize: '0.65rem' }}>
              {(alert.risk_level || 'UNKNOWN').replace('_', ' ')}
            </span>
            <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
              {new Date(alert.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
            </span>
          </div>
        </div>
        <div className="case-item-summary">
          {alert.transcription || 'No transcript available.'}
        </div>
        <div style={{ marginTop: '0.5rem', display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
          {alert.ambulance_dispatched && <span title="Ambulance Dispatched">🚑</span>}
          {alert.family_called && <span title="Family Called">📞</span>}
        </div>
      </div>
    );
  };

  const Section = ({ title, alerts, type, headerClass }: { title: string, alerts: Alert[], type: string, headerClass: string }) => (
    <section className="case-section">
      <div className={`case-section-header ${headerClass}`}>
        <span>{title}</span>
        <span className={`severity-badge badge-${type}`}>{alerts.length}</span>
      </div>
      <div className="case-list">
        {alerts.length > 0 ? (
          alerts.map(a => <CaseListItem key={a.id} alert={a} />)
        ) : (
          <div style={{ textAlign: 'center', padding: '2rem', color: 'var(--text-muted)', fontSize: '0.9rem' }}>Queue is empty</div>
        )}
      </div>
    </section>
  );

  return (
    <div className="dashboard-layout">
      <header>
        <div className="brand">
          <div className="brand-logo">💜</div>
          <div className="brand-name">GALE Alert Alarm</div>
        </div>
        <div className="monitoring-stats" style={{ display: 'flex', gap: '2rem', alignItems: 'center' }}>
          <div className="monitoring-count">{urgent.filter(a => !(a.ambulance_dispatched || a.family_called)).length} Pending Actions</div>
          <div style={{ color: 'var(--text-muted)', fontSize: '0.875rem' }}>Operator Dashboard</div>
        </div>
      </header>

      <main className="main-content">
        <div className="dashboard-stack">
          <Section title="🚨 URGENT ACTION REQUIRED" alerts={urgent} type="urgent" headerClass="header-urgent" />
          <div className="bottom-grid">
            <Section title="🟡 UNCERTAIN (NEEDS REVIEW)" alerts={uncertain} type="uncertain" headerClass="header-uncertain" />
            <Section title="🟠 NON-URGENT" alerts={nonUrgent} type="non-urgent" headerClass="header-non-urgent" />
            <Section title="🟢 FALSE ALARMS" alerts={falseAlarm} type="false-alarm" headerClass="header-false-alarm" />
          </div>
        </div>
      </main>

      {selectedCase && (
        <div className="modal-overlay">
          <div className="modal-card">
            <div className="focus-case-header" style={{ 
              background: selectedCase.risk_level === 'URGENT' ? 'var(--urgent)' : 
                          selectedCase.risk_level === 'NON_URGENT' ? 'var(--non-urgent)' :
                          selectedCase.risk_level === 'UNCERTAIN' ? 'var(--uncertain)' : 'var(--false-alarm)'
            }}>
              <span>🔍 CASE DETAILS: {selectedCase.seniors?.full_name}</span>
              <button className="close-btn" onClick={() => setSelectedCase(null)}>✕</button>
            </div>
            <div style={{ padding: '2rem' }}>
              {(selectedCase.risk_level === 'URGENT' || selectedCase.risk_level === 'UNCERTAIN') && (
                <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: '1rem' }}>
                  <div style={{ 
                      background: '#1e293b',
                      color: '#94a3b8',
                      border: '1px solid #334155',
                      padding: '0.4rem 1rem',
                      borderRadius: '99px',
                      fontSize: '0.75rem',
                      fontWeight: 700
                  }}>
                      ⚪ WAITING FOR ACTION
                  </div>
                </div>
              )}

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1.5rem', marginBottom: '1.5rem' }}>
                <div className="container-box">
                  <div style={{ fontSize: '0.75rem', fontWeight: 700, color: 'var(--text-muted)', marginBottom: '0.5rem' }}>LOCATION & CONTACT</div>
                  <div style={{ fontWeight: 700 }}>{selectedCase.seniors?.address || 'Address not listed'}</div>
                  <div style={{ fontSize: '0.9rem', marginTop: '0.5rem' }}>📞 {selectedCase.seniors?.phone_number || 'No phone'}</div>
                </div>
                <div className="container-box">
                  <div style={{ fontSize: '0.75rem', fontWeight: 700, color: 'var(--text-muted)', marginBottom: '0.5rem' }}>TRANSCRIPT</div>
                  <div style={{ fontSize: '1rem', fontStyle: 'italic', marginBottom: selectedCase.audio_url ? '1rem' : 0 }}>"{selectedCase.transcription}"</div>
                  {selectedCase.audio_url && (
                    <audio controls src={selectedCase.audio_url} style={{ width: '100%', height: '32px' }}>
                      Your browser does not support the audio element.
                    </audio>
                  )}
                </div>
              </div>

              <div className="action-grid" style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem', marginBottom: '1.5rem' }}>
                <button 
                  className="btn-emergency" 
                  style={{ opacity: selectedCase.ambulance_dispatched ? 1 : 0.8, background: selectedCase.ambulance_dispatched ? 'var(--urgent)' : '#450a0a', color: selectedCase.ambulance_dispatched ? 'white' : '#f87171', border: selectedCase.ambulance_dispatched ? 'none' : '1px solid #7f1d1d' }}
                  onClick={() => handleIntervention('ambulance')}
                >
                  {selectedCase.ambulance_dispatched ? '✅ AMBULANCE EN ROUTE' : '🚑 DISPATCH AMBULANCE'}
                </button>
                <button 
                  className="btn-family" 
                  style={{ opacity: selectedCase.family_called ? 1 : 0.8, background: selectedCase.family_called ? 'var(--safe)' : '#172554', color: selectedCase.family_called ? 'white' : '#60a5fa', border: selectedCase.family_called ? 'none' : '1px solid #1e3a8a' }}
                  onClick={() => handleIntervention('family')}
                >
                  {selectedCase.family_called ? '✅ FAMILY CONTACTED' : '📞 CALL FAMILY MEMBER'}
                </button>
              </div>

              <hr style={{ margin: '1.5rem 0', border: 'none', borderTop: '1px solid var(--border)' }} />

              <div style={{ marginBottom: '1rem' }}>
                <label style={{ display: 'block', fontWeight: 700, marginBottom: '0.5rem', fontSize: '0.8rem' }}>AI REINFORCEMENT</label>
                <div style={{ display: 'flex', gap: '1rem', alignItems: 'center' }}>
                  <select 
                    style={{ 
                      flex: 1, 
                      padding: '0.75rem', 
                      borderRadius: '0.75rem', 
                      border: '1px solid var(--border)', 
                      fontSize: '1rem', 
                      fontWeight: 600,
                      background: '#162032',
                      color: 'var(--text-main)',
                      outline: 'none'
                    }}
                    value={newSeverity}
                    onChange={(e) => setNewSeverity(e.target.value)}
                  >
                    <option value="URGENT">🔴 URGENT</option>
                    <option value="NON_URGENT">🟠 NON-URGENT</option>
                    <option value="UNCERTAIN">🟡 UNCERTAIN</option>
                    <option value="FALSE_ALARM">🟢 FALSE ALARM</option>
                  </select>
                  <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', cursor: 'pointer', fontSize: '0.9rem' }}>
                    <input type="checkbox" checked={saveAsExample} onChange={(e) => setSaveAsExample(e.target.checked)} />
                    Add use case to AI example
                  </label>
                </div>
              </div>

              {newSeverity === 'URGENT' && (!selectedCase.ambulance_dispatched || !selectedCase.family_called) && (
                <div style={{ color: 'var(--urgent)', fontSize: '0.8rem', fontWeight: 700, textAlign: 'center', marginBottom: '0.5rem' }}>
                  ⚠️ Ambulance + Family contact required for urgent cases
                </div>
              )}

              <button 
                className="action-btn" 
                style={{ 
                  width: '100%', 
                  padding: '1.25rem', 
                  fontSize: '1.25rem', 
                  marginTop: '1rem',
                  opacity: (
                    (selectedCase.risk_level === 'UNCERTAIN' && newSeverity === 'UNCERTAIN') ||
                    (newSeverity === 'URGENT' && (!selectedCase.ambulance_dispatched || !selectedCase.family_called))
                  ) ? 0.5 : 1,
                  cursor: (
                    (selectedCase.risk_level === 'UNCERTAIN' && newSeverity === 'UNCERTAIN') ||
                    (newSeverity === 'URGENT' && (!selectedCase.ambulance_dispatched || !selectedCase.family_called))
                  ) ? 'not-allowed' : 'pointer'
                }} 
                onClick={handleSave}
                disabled={
                    (selectedCase.risk_level === 'UNCERTAIN' && newSeverity === 'UNCERTAIN') ||
                    (newSeverity === 'URGENT' && (!selectedCase.ambulance_dispatched || !selectedCase.family_called))
                }
              >
                SAVE & UPDATE
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default App;
