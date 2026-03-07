import React, { useEffect, useMemo, useState } from 'react';
import './index.css';

type RiskLevel = 'URGENT' | 'NON_URGENT' | 'UNCERTAIN' | 'FALSE_ALARM';
type DashboardTab = 'to_handle' | 'closed' | 'seniors' | 'settings';

interface Alert {
  id: string;
  senior_id: string;
  risk_level: RiskLevel;
  risk_score?: number | null;
  ai_assessment?: string | null;
  analysis_summary?: string | null;
  keywords?: string[] | null;
  transcription?: string | null;
  translated_text?: string | null;
  language_detected?: string | null;
  senior_response?: string | null;
  audio_url?: string | null;
  status?: string | null;
  is_resolved?: boolean | null;
  created_at: string;
  ambulance_dispatched?: boolean | null;
  dispatch_ambulance_at?: string | null;
  family_called?: boolean | null;
  family_called_at?: string | null;
  is_attended?: boolean | null;
  operator_actions?: OperatorActionRecord[];
  seniors?: {
    id?: string;
    full_name: string;
    phone_number?: string;
    address?: string;
    preferred_language?: string;
  };
}

interface ConversationReply {
  created_at?: string;
  english_text?: string | null;
  original_text?: string | null;
  source_language?: string | null;
  translated?: boolean;
  has_voice?: boolean;
  audio_url?: string | null;
}

interface FewShotExample {
  id: string;
  transcript: string;
  risk_level: RiskLevel;
  created_at?: string;
}

interface SeniorOverview {
  id: string;
  full_name: string;
  phone_number?: string;
  address?: string;
  preferred_language?: string;
  medical_notes?: string;
  open_cases: number;
  total_cases: number;
  latest_alert?: {
    id: string;
    risk_level?: RiskLevel;
    status?: string;
    created_at?: string;
  };
}

interface EmergencyContact {
  id: string;
  senior_id: string;
  name: string;
  relationship?: string | null;
  phone_number?: string | null;
  telegram_user_id?: string | null;
  priority_order: number;
  notify_on_uncertain: boolean;
}

interface AlertOverridePayload {
  risk_level?: RiskLevel;
  is_resolved?: boolean;
  status?: string;
  operator?: string;
  operator_actions?: OperatorActionInput[];
}

interface OperatorActionInput {
  actions_taken: string;
  action_time: string;
  action_payload?: Record<string, unknown>;
}

interface OperatorActionRecord {
  case_id: string;
  operator: string;
  actions_taken: string;
  action_payload?: Record<string, unknown>;
  action_time?: string;
}

interface NewContactDraft {
  name: string;
  relationship: string;
  phone_number: string;
  telegram_user_id: string;
  priority_order: number;
  notify_on_uncertain: boolean;
}

const defaultContactDraft: NewContactDraft = {
  name: '',
  relationship: '',
  phone_number: '',
  telegram_user_id: '',
  priority_order: 1,
  notify_on_uncertain: false,
};

const isClosedAlert = (alert: Alert): boolean => {
  return alert.is_resolved === true || (alert.status || '').toLowerCase() === 'closed';
};

const LANGUAGE_LABELS: Record<string, string> = {
  en: 'English',
  zh: 'Chinese',
  ms: 'Malay',
  ta: 'Tamil',
  nan: 'Hokkien',
  yue: 'Cantonese',
};

const getLanguageLabel = (language?: string | null): string => {
  const key = (language || '').trim().toLowerCase();
  if (!key) return '-';
  return LANGUAGE_LABELS[key] || language || '-';
};

const getEnglishViewText = (alert: Alert): string => {
  const english = (alert.translated_text || '').trim();
  if (english) return english;
  return (alert.transcription || '').trim();
};

const isAlertTranslated = (alert: Alert): boolean => {
  const language = (alert.language_detected || '').toLowerCase();
  return Boolean(alert.translated_text && language && language !== 'en');
};

const resolveAudioUrl = (audioUrl?: string | null): string | null => {
  if (!audioUrl) return null;
  if (audioUrl.startsWith('http://') || audioUrl.startsWith('https://')) return audioUrl;

  const supabaseUrl = import.meta.env.VITE_SUPABASE_URL;
  const bucket = import.meta.env.VITE_SUPABASE_AUDIO_BUCKET || 'alerts-audio';
  if (!supabaseUrl) return null;

  const rawPath = audioUrl.replace(/^\/+/, '');
  if (rawPath.startsWith('storage/v1/object/public/')) {
    return `${supabaseUrl}/${rawPath}`;
  }
  if (rawPath.startsWith('object/public/')) {
    return `${supabaseUrl}/storage/v1/${rawPath}`;
  }

  const path = rawPath.startsWith(`${bucket}/`) ? rawPath.slice(bucket.length + 1) : rawPath;
  return `${supabaseUrl}/storage/v1/object/public/${bucket}/${path}`;
};

const toDateTimeLocalValue = (source?: string | Date | null): string => {
  const date = source ? new Date(source) : new Date();
  if (Number.isNaN(date.getTime())) return '';
  const offsetMs = date.getTimezoneOffset() * 60000;
  return new Date(date.getTime() - offsetMs).toISOString().slice(0, 16);
};

const toIsoFromDateTimeLocal = (value: string): string => {
  if (!value) return new Date().toISOString();
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? new Date().toISOString() : parsed.toISOString();
};

const getAssessmentText = (alert: Alert): string => {
  const direct = (alert.ai_assessment || '').trim();
  if (direct) return direct;

  const summary = (alert.analysis_summary || '').trim();
  if (!summary) return 'No AI assessment available.';

  const marker = 'Assessment:';
  const markerIndex = summary.indexOf(marker);
  if (markerIndex >= 0) {
    const extracted = summary.slice(markerIndex + marker.length).trim();
    if (extracted) return extracted;
  }
  return summary;
};

const App: React.FC = () => {
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [fewShotExamples, setFewShotExamples] = useState<FewShotExample[]>([]);
  const [fewShotTranscript, setFewShotTranscript] = useState('');
  const [fewShotRisk, setFewShotRisk] = useState<RiskLevel>('UNCERTAIN');
  const [riskPrompt, setRiskPrompt] = useState('');
  const [riskPromptDraft, setRiskPromptDraft] = useState('');
  const [isSavingPrompt, setIsSavingPrompt] = useState(false);

  const [seniors, setSeniors] = useState<SeniorOverview[]>([]);
  const [contactModalSenior, setContactModalSenior] = useState<SeniorOverview | null>(null);
  const [contactsBySenior, setContactsBySenior] = useState<Record<string, EmergencyContact[]>>({});
  const [newContactBySenior, setNewContactBySenior] = useState<Record<string, NewContactDraft>>({});

  const [selectedCase, setSelectedCase] = useState<Alert | null>(null);
  const [dispatchAmbulanceNow, setDispatchAmbulanceNow] = useState(false);
  const [callFamilyNow, setCallFamilyNow] = useState(false);
  const [dispatchActionTime, setDispatchActionTime] = useState('');
  const [familyActionTime, setFamilyActionTime] = useState('');
  const [selectedFamilyContactIds, setSelectedFamilyContactIds] = useState<string[]>([]);
  const [caseContacts, setCaseContacts] = useState<EmergencyContact[]>([]);
  const [caseReplies, setCaseReplies] = useState<ConversationReply[]>([]);
  const [selectedCaseTab, setSelectedCaseTab] = useState<'details' | 'family'>('details');
  const [newSeverity, setNewSeverity] = useState<RiskLevel>('UNCERTAIN');
  const [activeTab, setActiveTab] = useState<DashboardTab>('to_handle');
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const fetchAlerts = async () => {
    const response = await fetch('/api/v1/operator/alerts?limit=100&include_closed=true');
    if (!response.ok) throw new Error(`Failed to fetch alerts (${response.status})`);
    const data = (await response.json()) as Alert[];
    setAlerts(Array.isArray(data) ? data : []);
  };

  const fetchFewShotExamples = async () => {
    const response = await fetch('/api/v1/operator/few-shot-examples?limit=30');
    if (!response.ok) throw new Error(`Failed to fetch few-shot examples (${response.status})`);
    const data = (await response.json()) as FewShotExample[];
    setFewShotExamples(Array.isArray(data) ? data : []);
  };

  const fetchSeniors = async () => {
    const response = await fetch('/api/v1/operator/seniors/overview');
    if (!response.ok) throw new Error(`Failed to fetch seniors (${response.status})`);
    const data = (await response.json()) as SeniorOverview[];
    setSeniors(Array.isArray(data) ? data : []);
  };

  const fetchRiskPrompt = async () => {
    const response = await fetch('/api/v1/operator/settings/risk-prompt');
    if (!response.ok) throw new Error(`Failed to fetch risk prompt (${response.status})`);
    const data = (await response.json()) as { key?: string; value?: string };
    const value = typeof data.value === 'string' ? data.value : '';
    setRiskPrompt(value);
    setRiskPromptDraft(value);
  };

  const fetchContactsForSenior = async (seniorId: string) => {
    const response = await fetch(`/api/v1/operator/seniors/${seniorId}/emergency-contacts`);
    if (!response.ok) throw new Error(`Failed to fetch contacts (${response.status})`);
    const data = (await response.json()) as EmergencyContact[];
    setContactsBySenior((prev) => ({ ...prev, [seniorId]: Array.isArray(data) ? data : [] }));
  };

  const fetchContactsForSelectedCase = async (seniorId: string) => {
    try {
      const response = await fetch(`/api/v1/operator/seniors/${seniorId}/emergency-contacts`);
      if (!response.ok) throw new Error(`Failed to fetch contacts (${response.status})`);
      const data = (await response.json()) as EmergencyContact[];
      setCaseContacts(Array.isArray(data) ? data : []);
    } catch (error) {
      setCaseContacts([]);
    }
  };

  const fetchConversationReplies = async (alertId: string) => {
    try {
      const response = await fetch(`/api/v1/operator/alerts/${alertId}/conversation-replies`);
      if (!response.ok) throw new Error(`Failed to fetch conversation replies (${response.status})`);
      const data = (await response.json()) as ConversationReply[];
      setCaseReplies(Array.isArray(data) ? data : []);
    } catch (error) {
      setCaseReplies([]);
    }
  };

  const fetchAll = async () => {
    try {
      await Promise.all([
        fetchAlerts(),
        fetchFewShotExamples(),
        fetchSeniors(),
        fetchRiskPrompt(),
      ]);
      setErrorMessage(null);
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Unknown dashboard error';
      setErrorMessage(message);
    }
  };

  useEffect(() => {
    fetchAll();
    const interval = setInterval(fetchAll, 5000);
    return () => clearInterval(interval);
  }, []);

  const updateAlertInDB = async (alertId: string, updates: AlertOverridePayload) => {
    const response = await fetch(`/api/v1/operator/alerts/${alertId}/override?save_as_example=false`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(updates),
    });
    if (!response.ok) throw new Error(`Failed to update alert (${response.status})`);

    const updatedRow = (await response.json()) as Alert;
    let mergedUpdatedRow = updatedRow;
    setAlerts((prev) =>
      prev.map((item) => {
        if (item.id !== updatedRow.id) return item;
        mergedUpdatedRow = { ...item, ...updatedRow, seniors: updatedRow.seniors || item.seniors };
        return mergedUpdatedRow;
      }),
    );
    await fetchSeniors();
    return mergedUpdatedRow;
  };

  const createFewShotExample = async () => {
    const transcript = fewShotTranscript.trim();
    if (!transcript) return;

    const response = await fetch('/api/v1/operator/few-shot-examples', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ transcript, risk_level: fewShotRisk }),
    });
    if (!response.ok) throw new Error(`Failed to create few-shot example (${response.status})`);

    setFewShotTranscript('');
    await fetchFewShotExamples();
  };

  const deleteFewShotExample = async (exampleId: string) => {
    const response = await fetch(`/api/v1/operator/few-shot-examples/${exampleId}`, { method: 'DELETE' });
    if (!response.ok) throw new Error(`Failed to delete example (${response.status})`);
    await fetchFewShotExamples();
  };

  const saveRiskPrompt = async () => {
    const value = riskPromptDraft.trim();
    if (!value) {
      alert('Prompt cannot be empty');
      return;
    }

    setIsSavingPrompt(true);
    try {
      const response = await fetch('/api/v1/operator/settings/risk-prompt', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ value }),
      });
      if (!response.ok) throw new Error(`Failed to save prompt (${response.status})`);
      const data = (await response.json()) as { value?: string };
      const saved = typeof data.value === 'string' ? data.value : value;
      setRiskPrompt(saved);
      setRiskPromptDraft(saved);
    } finally {
      setIsSavingPrompt(false);
    }
  };

  const updateFewShotExample = async (example: FewShotExample) => {
    const response = await fetch(`/api/v1/operator/few-shot-examples/${example.id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ transcript: example.transcript, risk_level: example.risk_level }),
    });
    if (!response.ok) throw new Error(`Failed to update example (${response.status})`);
    await fetchFewShotExamples();
  };

  const updateFewShotLocal = (exampleId: string, updates: Partial<FewShotExample>) => {
    setFewShotExamples((prev) =>
      prev.map((item) => (item.id === exampleId ? { ...item, ...updates } : item)),
    );
  };

  const handleSave = async () => {
    if (!selectedCase) return;

    const operatorActions: OperatorActionInput[] = [
      {
        actions_taken: 'mark_attended',
        action_time: new Date().toISOString(),
      },
    ];

    if (dispatchAmbulanceNow) {
      operatorActions.push({
        actions_taken: 'dispatch_ambulance',
        action_time: toIsoFromDateTimeLocal(dispatchActionTime),
      });
    }

    if (callFamilyNow) {
      if (selectedFamilyContactIds.length === 0) {
        alert('Please select at least one family member contacted.');
        return;
      }
      const selectedContacts = caseContacts.filter((contact) => selectedFamilyContactIds.includes(contact.id));
      operatorActions.push({
        actions_taken: 'call_family',
        action_time: toIsoFromDateTimeLocal(familyActionTime),
        action_payload: {
          contact_ids: selectedContacts.map((contact) => contact.id),
          contact_names: selectedContacts.map((contact) => contact.name),
        },
      });
    }

    const updates: AlertOverridePayload = {
      operator: 'Operator 1',
      operator_actions: operatorActions,
    };
    if (newSeverity !== selectedCase.risk_level) updates.risk_level = newSeverity;
    if (newSeverity === 'FALSE_ALARM') {
      updates.status = 'closed';
      updates.is_resolved = true;
    }

    try {
      const updatedCase = await updateAlertInDB(selectedCase.id, updates);
      await fetchAlerts();
      setDispatchAmbulanceNow(false);
      setCallFamilyNow(false);
      setDispatchActionTime('');
      setFamilyActionTime('');
      setSelectedFamilyContactIds([]);
      setSelectedCase(null);
      if (isClosedAlert(updatedCase)) {
        setActiveTab('closed');
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Action failed';
      alert(message);
    }
  };

  const handleCloseCase = async () => {
    if (!selectedCase) return;

    const updates: AlertOverridePayload = {
      status: 'closed',
      is_resolved: true,
      operator: 'Operator 1',
      operator_actions: [
        {
          actions_taken: 'close_case',
          action_time: new Date().toISOString(),
        },
      ],
    };

    try {
      await updateAlertInDB(selectedCase.id, updates);
      await fetchAlerts();
      setDispatchAmbulanceNow(false);
      setCallFamilyNow(false);
      setDispatchActionTime('');
      setFamilyActionTime('');
      setSelectedFamilyContactIds([]);
      setSelectedCase(null);
      setActiveTab('closed');
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to close case';
      alert(message);
    }
  };

  const handleIntervention = (type: 'ambulance' | 'family') => {
    if (!selectedCase) return;
    if (type === 'ambulance') {
      if (selectedCase.ambulance_dispatched || dispatchAmbulanceNow) return;
      setDispatchAmbulanceNow(true);
      setDispatchActionTime(toDateTimeLocalValue(new Date()));
    }
    if (type === 'family') {
      if (selectedCase.family_called || callFamilyNow) return;
      setCallFamilyNow(true);
      setFamilyActionTime(toDateTimeLocalValue(new Date()));
    }
  };

  const openCaseDetails = (alert: Alert) => {
    setSelectedCase(alert);
    setNewSeverity(alert.risk_level);
    setDispatchAmbulanceNow(false);
    setCallFamilyNow(false);
    setDispatchActionTime(toDateTimeLocalValue(alert.dispatch_ambulance_at || new Date()));
    setFamilyActionTime(toDateTimeLocalValue(alert.family_called_at || new Date()));
    setSelectedFamilyContactIds([]);
    setSelectedCaseTab('details');
    fetchConversationReplies(alert.id);
    if (alert.seniors?.id) {
      fetchContactsForSelectedCase(alert.seniors.id);
    } else {
      setCaseContacts([]);
    }
  };

  const openContactManager = async (senior: SeniorOverview) => {
    setContactModalSenior(senior);
    if (!contactsBySenior[senior.id]) {
      try {
        await fetchContactsForSenior(senior.id);
      } catch (error) {
        const message = error instanceof Error ? error.message : 'Failed to load contacts';
        alert(message);
      }
    }
  };

  const addCaseAsFewShotExample = async (caseItem: Alert, riskLevel: RiskLevel) => {
    const transcript =
      riskLevel === 'FALSE_ALARM'
        ? getEnglishViewText(caseItem).trim()
        : (caseItem.transcription || '').trim();
    if (!transcript) {
      alert('No transcript available for this case.');
      return;
    }
    const response = await fetch('/api/v1/operator/few-shot-examples', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ transcript, risk_level: riskLevel }),
    });
    if (!response.ok) throw new Error(`Failed to add case as example (${response.status})`);
    await fetchFewShotExamples();
  };

  const updateDraftForSenior = (seniorId: string, partial: Partial<NewContactDraft>) => {
    setNewContactBySenior((prev) => ({
      ...prev,
      [seniorId]: { ...(prev[seniorId] || defaultContactDraft), ...partial },
    }));
  };

  const createContactForSenior = async (seniorId: string) => {
    const draft = newContactBySenior[seniorId] || defaultContactDraft;
    if (!draft.name.trim()) {
      alert('Contact name is required');
      return;
    }

    const response = await fetch(`/api/v1/operator/seniors/${seniorId}/emergency-contacts`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        senior_id: seniorId,
        name: draft.name.trim(),
        relationship: draft.relationship.trim() || null,
        phone_number: draft.phone_number.trim() || null,
        telegram_user_id: draft.telegram_user_id.trim() || null,
        priority_order: Number(draft.priority_order) || 1,
        notify_on_uncertain: Boolean(draft.notify_on_uncertain),
      }),
    });
    if (!response.ok) throw new Error(`Failed to create contact (${response.status})`);

    setNewContactBySenior((prev) => ({ ...prev, [seniorId]: { ...defaultContactDraft } }));
    await fetchContactsForSenior(seniorId);
  };

  const updateContactField = (
    seniorId: string,
    contactId: string,
    field: keyof EmergencyContact,
    value: string | number | boolean,
  ) => {
    setContactsBySenior((prev) => ({
      ...prev,
      [seniorId]: (prev[seniorId] || []).map((contact) =>
        contact.id === contactId ? { ...contact, [field]: value } : contact,
      ),
    }));
  };

  const saveContact = async (seniorId: string, contact: EmergencyContact) => {
    const response = await fetch(`/api/v1/operator/emergency-contacts/${contact.id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name: contact.name,
        relationship: contact.relationship || null,
        phone_number: contact.phone_number || null,
        telegram_user_id: contact.telegram_user_id || null,
        priority_order: Number(contact.priority_order) || 1,
        notify_on_uncertain: Boolean(contact.notify_on_uncertain),
      }),
    });
    if (!response.ok) throw new Error(`Failed to update contact (${response.status})`);
    await fetchContactsForSenior(seniorId);
  };

  const deleteContact = async (seniorId: string, contactId: string) => {
    const response = await fetch(`/api/v1/operator/emergency-contacts/${contactId}`, {
      method: 'DELETE',
    });
    if (!response.ok) throw new Error(`Failed to delete contact (${response.status})`);
    await fetchContactsForSenior(seniorId);
  };

  const sortedAlertsNewestFirst = useMemo(
    () => [...alerts].sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()),
    [alerts],
  );

  const openAlerts = useMemo(
    () =>
      sortedAlertsNewestFirst
        .filter((a) => !isClosedAlert(a))
        .sort((a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime()),
    [sortedAlertsNewestFirst],
  );
  const closedAlerts = useMemo(
    () => sortedAlertsNewestFirst.filter(isClosedAlert),
    [sortedAlertsNewestFirst],
  );
  const urgent = openAlerts.filter((a) => a.risk_level === 'URGENT');
  const nonUrgent = openAlerts.filter((a) => a.risk_level === 'NON_URGENT');
  const uncertain = openAlerts.filter((a) => a.risk_level === 'UNCERTAIN');
  const falseAlarm = openAlerts.filter((a) => a.risk_level === 'FALSE_ALARM');
  const casesToHandleCount = urgent.length + nonUrgent.length + uncertain.length + falseAlarm.length;
  const pendingActions = urgent.filter((a) => !a.ambulance_dispatched || !a.family_called).length;

  const CaseListItem = ({ alert }: { alert: Alert }) => {
    const isHandled =
      alert.risk_level === 'URGENT' &&
      Boolean(alert.is_attended) &&
      Boolean(alert.ambulance_dispatched) &&
      Boolean(alert.family_called);

    return (
      <div
        className={`case-item ${isHandled ? 'handled-item' : ''}`}
        onClick={() => openCaseDetails(alert)}
      >
        <div className="case-item-header">
          <span style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            {alert.seniors?.full_name || 'Unknown Senior'}
            {isAlertTranslated(alert) && (
              <span className="severity-badge badge-uncertain" style={{ fontSize: '0.58rem', padding: '1px 6px' }}>
                Translated
              </span>
            )}
            {isHandled && (
              <span
                style={{
                  fontSize: '0.6rem',
                  background: '#334155',
                  color: '#94a3b8',
                  padding: '1px 5px',
                  borderRadius: '4px',
                  fontWeight: 700,
                }}
              >
                HANDLED
              </span>
            )}
          </span>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <span
              className={`severity-badge badge-${(alert.risk_level || 'UNKNOWN').toLowerCase().replace('_', '-')}`}
              style={{ fontSize: '0.65rem' }}
            >
              {(alert.risk_level || 'UNKNOWN').replace('_', ' ')}
            </span>
            <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
              {new Date(alert.created_at).toLocaleTimeString([], {
                hour: '2-digit',
                minute: '2-digit',
              })}
            </span>
          </div>
        </div>
        <div className="case-item-summary">{getEnglishViewText(alert) || 'No transcript available.'}</div>
      </div>
    );
  };

  const Section = ({
    title,
    list,
    type,
    headerClass,
  }: {
    title: string;
    list: Alert[];
    type: string;
    headerClass: string;
  }) => (
    <section className="case-section">
      <div className={`case-section-header ${headerClass}`}>
        <span>{title}</span>
        <span className={`severity-badge badge-${type}`}>{list.length}</span>
      </div>
      <div className="case-list">
        {list.length > 0 ? (
          list.map((a) => <CaseListItem key={a.id} alert={a} />)
        ) : (
          <div
            style={{
              textAlign: 'center',
              padding: '2rem',
              color: 'var(--text-muted)',
              fontSize: '0.9rem',
            }}
          >
            Queue is empty
          </div>
        )}
      </div>
    </section>
  );

  return (
    <div className="dashboard-layout">
      <header>
        <div className="brand">
          <div className="brand-logo">🛟</div>
          <div className="brand-name">GALE Alert Plus</div>
        </div>
        <div className="monitoring-stats" style={{ display: 'flex', gap: '2rem', alignItems: 'center' }}>
          <div className="monitoring-count">{pendingActions} Pending Actions</div>
          <div style={{ color: 'var(--text-muted)', fontSize: '0.875rem' }}>Operator 1</div>
          <button
            className={`header-nav-btn ${activeTab === 'settings' ? 'active' : ''}`}
            onClick={() => setActiveTab('settings')}
          >
            Settings
          </button>
        </div>
      </header>

      <main className="main-content">
        <div className="dashboard-tabs" role="tablist" aria-label="Dashboard tabs">
          <button
            className={`dashboard-tab-btn ${activeTab === 'to_handle' ? 'active' : ''}`}
            onClick={() => setActiveTab('to_handle')}
          >
            Cases To Handle ({casesToHandleCount})
          </button>
          <button
            className={`dashboard-tab-btn ${activeTab === 'closed' ? 'active' : ''}`}
            onClick={() => setActiveTab('closed')}
          >
            Cases Closed ({closedAlerts.length})
          </button>
          <button
            className={`dashboard-tab-btn ${activeTab === 'seniors' ? 'active' : ''}`}
            onClick={() => setActiveTab('seniors')}
          >
            Senior Dashboard ({seniors.length})
          </button>
        </div>

        {errorMessage && <div className="dashboard-error">{errorMessage}</div>}

        {activeTab === 'to_handle' && (
          <div className="dashboard-stack">
            <Section title="URGENT ACTION REQUIRED" list={urgent} type="urgent" headerClass="header-urgent" />
            <div className="bottom-grid">
              <Section title="UNCERTAIN (NEEDS REVIEW)" list={uncertain} type="uncertain" headerClass="header-uncertain" />
              <Section title="NON-URGENT" list={nonUrgent} type="non-urgent" headerClass="header-non-urgent" />
              <Section title="FALSE ALARMS" list={falseAlarm} type="false-alarm" headerClass="header-false-alarm" />
            </div>
          </div>
        )}

        {activeTab === 'closed' && (
          <section className="case-section">
            <div className="case-section-header header-false-alarm">
              <span>Closed Cases</span>
              <span className="severity-badge badge-false-alarm">{closedAlerts.length}</span>
            </div>
            <div className="case-list">
              {closedAlerts.map((alert) => (
                <div
                  key={alert.id}
                  className="case-item"
                  onClick={() => openCaseDetails(alert)}
                >
                  <div className="case-item-header">
                    <span>{alert.seniors?.full_name || 'Unknown Senior'}</span>
                    <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                      {new Date(alert.created_at).toLocaleString()}
                    </span>
                  </div>
                  <div className="case-item-summary">{getEnglishViewText(alert) || 'No transcript available.'}</div>
                </div>
              ))}
              {closedAlerts.length === 0 && (
                <div style={{ textAlign: 'center', padding: '2rem', color: 'var(--text-muted)', fontSize: '0.9rem' }}>
                  No closed cases yet
                </div>
              )}
            </div>
          </section>
        )}

        {activeTab === 'seniors' && (
          <section className="case-section senior-dashboard-section">
            <div className="case-section-header senior-dashboard-header">
              <span>Senior Overview</span>
              <span className="severity-badge">{seniors.length} seniors</span>
            </div>
            <div className="senior-grid">
              {seniors.map((senior) => {
                return (
                  <article key={senior.id} className="senior-card">
                    <div className="senior-card-top">
                      <h3>{senior.full_name}</h3>
                      <span className="severity-badge">Open: {senior.open_cases}</span>
                    </div>
                    <p>Phone: {senior.phone_number || '-'}</p>
                    <p>Language: {getLanguageLabel(senior.preferred_language)}</p>
                    <p>Address: {senior.address || '-'}</p>
                    <p>
                      Latest: {senior.latest_alert?.risk_level || '-'} / {senior.latest_alert?.status || '-'}
                    </p>

                    <button
                      className="dashboard-tab-btn"
                      style={{ marginTop: '0.5rem' }}
                      onClick={() => openContactManager(senior)}
                    >
                      View Details & Contacts
                    </button>
                  </article>
                );
              })}
              {seniors.length === 0 && (
                <div style={{ textAlign: 'center', padding: '2rem', color: 'var(--text-muted)', fontSize: '0.9rem' }}>
                  No seniors found
                </div>
              )}
            </div>
          </section>
        )}

        {activeTab === 'settings' && (
          <div className="dashboard-stack">
            <section className="case-section">
              <div className="case-section-header">
                <span>AI Prompt Settings</span>
                <span className="severity-badge">risk_classification_system_prompt</span>
              </div>
              <div className="prompt-config-wrap">
                <p className="prompt-item-text">
                  This is the base system prompt used by risk classification. Keep
                  <code> {'{few_shot_examples}'} </code>
                  placeholder in the template.
                </p>
                <textarea
                  className="prompt-input"
                  style={{ minHeight: '300px' }}
                  value={riskPromptDraft}
                  onChange={(e) => setRiskPromptDraft(e.target.value)}
                />
                <div className="mini-row">
                  <button className="action-btn" disabled={isSavingPrompt} onClick={saveRiskPrompt}>
                    {isSavingPrompt ? 'Saving...' : 'Save Prompt'}
                  </button>
                  <button
                    className="dashboard-tab-btn"
                    onClick={() => setRiskPromptDraft(riskPrompt)}
                    disabled={isSavingPrompt}
                  >
                    Revert
                  </button>
                </div>
              </div>
            </section>

            <section className="case-section">
              <div className="case-section-header">
                <span>Few Shot Examples</span>
                <span className="severity-badge">{fewShotExamples.length}</span>
              </div>
              <div className="prompt-config-wrap">
                <div className="prompt-form-row">
                  <textarea
                    className="prompt-input"
                    placeholder="Add transcript example used for AI prompting"
                    value={fewShotTranscript}
                    onChange={(e) => setFewShotTranscript(e.target.value)}
                  />
                </div>
                <div className="prompt-form-row">
                  <select
                    className="prompt-select"
                    value={fewShotRisk}
                    onChange={(e) => setFewShotRisk(e.target.value as RiskLevel)}
                  >
                    <option value="URGENT">URGENT</option>
                    <option value="NON_URGENT">NON_URGENT</option>
                    <option value="UNCERTAIN">UNCERTAIN</option>
                    <option value="FALSE_ALARM">FALSE_ALARM</option>
                  </select>
                  <button
                    className="action-btn"
                    onClick={async () => {
                      try {
                        await createFewShotExample();
                      } catch (error) {
                        const message = error instanceof Error ? error.message : 'Failed to create prompt example';
                        alert(message);
                      }
                    }}
                  >
                    Add Example
                  </button>
                </div>

                <div className="prompt-list">
                  {fewShotExamples.map((example) => (
                    <div key={example.id} className="prompt-item">
                      <div className="prompt-item-top">
                        <select
                          className="prompt-select"
                          value={example.risk_level}
                          onChange={(e) =>
                            updateFewShotLocal(example.id, {
                              risk_level: e.target.value as RiskLevel,
                            })
                          }
                        >
                          <option value="URGENT">URGENT</option>
                          <option value="NON_URGENT">NON_URGENT</option>
                          <option value="UNCERTAIN">UNCERTAIN</option>
                          <option value="FALSE_ALARM">FALSE_ALARM</option>
                        </select>
                        <div className="mini-row">
                          <button
                            className="action-btn"
                            onClick={async () => {
                              try {
                                await updateFewShotExample(example);
                              } catch (error) {
                                const message =
                                  error instanceof Error ? error.message : 'Failed to update example';
                                alert(message);
                              }
                            }}
                          >
                            Save
                          </button>
                          <button
                            className="danger-btn"
                            onClick={async () => {
                              try {
                                await deleteFewShotExample(example.id);
                              } catch (error) {
                                const message =
                                  error instanceof Error ? error.message : 'Failed to delete example';
                                alert(message);
                              }
                            }}
                          >
                            Delete
                          </button>
                        </div>
                      </div>
                      <textarea
                        className="prompt-input"
                        value={example.transcript}
                        onChange={(e) =>
                          updateFewShotLocal(example.id, {
                            transcript: e.target.value,
                          })
                        }
                      />
                    </div>
                  ))}
                </div>
              </div>
            </section>
          </div>
        )}
      </main>

      {contactModalSenior && (
        <div className="modal-overlay">
          <div className="modal-card" style={{ maxWidth: '760px', width: '100%', maxHeight: '88vh', overflow: 'hidden' }}>
            <div className="focus-case-header" style={{ background: '#1e3a8a' }}>
              <span>Family Contacts: {contactModalSenior.full_name}</span>
              <button className="close-btn" onClick={() => setContactModalSenior(null)}>
                x
              </button>
            </div>
            <div style={{ padding: '1.25rem 1.5rem 1.5rem', overflowY: 'auto', maxHeight: 'calc(88vh - 72px)' }}>
              <div className="container-box" style={{ marginBottom: '0.75rem' }}>
                <div style={{ fontWeight: 700, marginBottom: '0.5rem' }}>Senior Details</div>
                <div style={{ fontSize: '0.9rem', marginBottom: '0.25rem' }}>
                  <strong>Address:</strong> {contactModalSenior.address || 'Not listed'}
                </div>
                <div style={{ fontSize: '0.9rem', marginBottom: '0.25rem' }}>
                  <strong>Phone:</strong> {contactModalSenior.phone_number || 'Not listed'}
                </div>
                <div style={{ fontSize: '0.9rem', marginBottom: '0.75rem' }}>
                  <strong>Language:</strong> {getLanguageLabel(contactModalSenior.preferred_language)}
                </div>
                <div style={{ fontWeight: 700, marginBottom: '0.25rem' }}>Medical Notes</div>
                <div style={{ color: 'var(--text-muted)', maxHeight: '130px', overflowY: 'auto', whiteSpace: 'pre-wrap' }}>
                  {contactModalSenior.medical_notes || 'No medical notes provided'}
                </div>
              </div>

              <div style={{ fontWeight: 700, marginBottom: '0.5rem' }}>Family Contacts</div>

              <div className="contact-panel" style={{ maxHeight: '55vh', overflowY: 'auto', paddingRight: '0.25rem' }}>
                {(contactsBySenior[contactModalSenior.id] || []).map((contact) => (
                  <div key={contact.id} className="contact-item">
                    <input
                      className="mini-input"
                      value={contact.name}
                      onChange={(e) => updateContactField(contactModalSenior.id, contact.id, 'name', e.target.value)}
                      placeholder="Name"
                    />
                    <input
                      className="mini-input"
                      value={contact.relationship || ''}
                      onChange={(e) => updateContactField(contactModalSenior.id, contact.id, 'relationship', e.target.value)}
                      placeholder="Relationship"
                    />
                    <input
                      className="mini-input"
                      value={contact.phone_number || ''}
                      onChange={(e) => updateContactField(contactModalSenior.id, contact.id, 'phone_number', e.target.value)}
                      placeholder="Phone"
                    />
                    <input
                      className="mini-input"
                      value={contact.telegram_user_id || ''}
                      onChange={(e) => updateContactField(contactModalSenior.id, contact.id, 'telegram_user_id', e.target.value)}
                      placeholder="Telegram user ID"
                    />
                    <div className="mini-row">
                      <label style={{ fontSize: '0.8rem' }}>
                        Priority
                        <input
                          className="mini-input"
                          type="number"
                          value={contact.priority_order}
                          onChange={(e) =>
                            updateContactField(
                              contactModalSenior.id,
                              contact.id,
                              'priority_order',
                              Number(e.target.value) || 1,
                            )
                          }
                        />
                      </label>
                      <label style={{ fontSize: '0.8rem' }}>
                        <input
                          type="checkbox"
                          checked={Boolean(contact.notify_on_uncertain)}
                          onChange={(e) =>
                            updateContactField(
                              contactModalSenior.id,
                              contact.id,
                              'notify_on_uncertain',
                              e.target.checked,
                            )
                          }
                        />{' '}
                        Notify on uncertain
                      </label>
                    </div>
                    <div className="mini-row">
                      <button
                        className="action-btn"
                        onClick={async () => {
                          try {
                            await saveContact(contactModalSenior.id, contact);
                          } catch (error) {
                            const message = error instanceof Error ? error.message : 'Failed to save contact';
                            alert(message);
                          }
                        }}
                      >
                        Save
                      </button>
                      <button
                        className="danger-btn"
                        onClick={async () => {
                          try {
                            await deleteContact(contactModalSenior.id, contact.id);
                          } catch (error) {
                            const message = error instanceof Error ? error.message : 'Failed to delete contact';
                            alert(message);
                          }
                        }}
                      >
                        Remove
                      </button>
                    </div>
                  </div>
                ))}

                <div className="contact-item new-contact-item">
                  <h4>Add Contact</h4>
                  <input
                    className="mini-input"
                    value={(newContactBySenior[contactModalSenior.id] || defaultContactDraft).name}
                    onChange={(e) => updateDraftForSenior(contactModalSenior.id, { name: e.target.value })}
                    placeholder="Name"
                  />
                  <input
                    className="mini-input"
                    value={(newContactBySenior[contactModalSenior.id] || defaultContactDraft).relationship}
                    onChange={(e) => updateDraftForSenior(contactModalSenior.id, { relationship: e.target.value })}
                    placeholder="Relationship"
                  />
                  <input
                    className="mini-input"
                    value={(newContactBySenior[contactModalSenior.id] || defaultContactDraft).phone_number}
                    onChange={(e) => updateDraftForSenior(contactModalSenior.id, { phone_number: e.target.value })}
                    placeholder="Phone"
                  />
                  <input
                    className="mini-input"
                    value={(newContactBySenior[contactModalSenior.id] || defaultContactDraft).telegram_user_id}
                    onChange={(e) => updateDraftForSenior(contactModalSenior.id, { telegram_user_id: e.target.value })}
                    placeholder="Telegram user ID"
                  />
                  <div className="mini-row">
                    <label style={{ fontSize: '0.8rem' }}>
                      Priority
                      <input
                        className="mini-input"
                        type="number"
                        value={(newContactBySenior[contactModalSenior.id] || defaultContactDraft).priority_order}
                        onChange={(e) =>
                          updateDraftForSenior(contactModalSenior.id, {
                            priority_order: Number(e.target.value) || 1,
                          })
                        }
                      />
                    </label>
                    <label style={{ fontSize: '0.8rem' }}>
                      <input
                        type="checkbox"
                        checked={Boolean((newContactBySenior[contactModalSenior.id] || defaultContactDraft).notify_on_uncertain)}
                        onChange={(e) =>
                          updateDraftForSenior(contactModalSenior.id, {
                            notify_on_uncertain: e.target.checked,
                          })
                        }
                      />{' '}
                      Notify on uncertain
                    </label>
                  </div>
                  <button
                    className="action-btn"
                    onClick={async () => {
                      try {
                        await createContactForSenior(contactModalSenior.id);
                      } catch (error) {
                        const message = error instanceof Error ? error.message : 'Failed to add contact';
                        alert(message);
                      }
                    }}
                  >
                    Add Contact
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {selectedCase && (
        <div className="modal-overlay">
          <div className="modal-card case-modal-card">
            <div
              className="focus-case-header"
              style={{
                background:
                  selectedCase.risk_level === 'URGENT'
                    ? 'var(--urgent)'
                    : selectedCase.risk_level === 'NON_URGENT'
                      ? 'var(--non-urgent)'
                      : selectedCase.risk_level === 'UNCERTAIN'
                        ? 'var(--uncertain)'
                        : 'var(--false-alarm)',
              }}
            >
              <span>CASE DETAILS: {selectedCase.seniors?.full_name}</span>
              <button className="close-btn" onClick={() => setSelectedCase(null)}>
                x
              </button>
            </div>
            <div className="case-modal-body">
              <div className="dashboard-tabs" role="tablist" style={{ marginBottom: '1.5rem' }}>
                <button
                  className={`dashboard-tab-btn ${selectedCaseTab === 'details' ? 'active' : ''}`}
                  onClick={() => setSelectedCaseTab('details')}
                >
                  Details
                </button>
                <button
                  className={`dashboard-tab-btn ${selectedCaseTab === 'family' ? 'active' : ''}`}
                  onClick={() => setSelectedCaseTab('family')}
                >
                  Family Contacts ({caseContacts.length})
                </button>
              </div>

              {selectedCaseTab === 'details' && (
                <>
                  <div
                    style={{
                      display: 'grid',
                      gridTemplateColumns: '1fr 1fr',
                      gap: '1.5rem',
                      marginBottom: '1.5rem',
                    }}
                  >
                    <div className="container-box">
                      <div
                        style={{
                          fontSize: '0.75rem',
                          fontWeight: 700,
                          color: 'var(--text-muted)',
                          marginBottom: '0.5rem',
                        }}
                      >
                        LOCATION & CONTACT
                      </div>
                      <div style={{ fontWeight: 700 }}>{selectedCase.seniors?.address || 'Address not listed'}</div>
                      <div style={{ fontSize: '0.9rem', marginTop: '0.5rem' }}>
                        Phone: {selectedCase.seniors?.phone_number || 'No phone'}
                      </div>
                    </div>
                    <div className="container-box">
                      <div
                        style={{
                          fontSize: '0.75rem',
                          fontWeight: 700,
                          color: 'var(--text-muted)',
                          marginBottom: '0.5rem',
                        }}
                      >
                        TRANSCRIPT
                      </div>
                      {isAlertTranslated(selectedCase) && (
                        <div style={{ marginBottom: '0.5rem' }}>
                          <span className="severity-badge badge-uncertain">Translated to English</span>
                        </div>
                      )}
                      <div
                        style={{
                          fontSize: '1rem',
                          fontStyle: 'italic',
                          marginBottom: '0.6rem',
                        }}
                      >
                        "{getEnglishViewText(selectedCase) || 'No transcript'}"
                      </div>
                      {isAlertTranslated(selectedCase) && (
                        <div style={{ fontSize: '0.86rem', color: 'var(--text-muted)', marginBottom: '0.8rem' }}>
                          Original: "{selectedCase.transcription || '-'}"
                        </div>
                      )}
                      {resolveAudioUrl(selectedCase.audio_url) && (
                        <>
                          <audio
                            controls
                            src={resolveAudioUrl(selectedCase.audio_url) || undefined}
                            style={{ width: '100%', height: '32px' }}
                          >
                            Your browser does not support the audio element.
                          </audio>
                          <a
                            href={resolveAudioUrl(selectedCase.audio_url) || '#'}
                            target="_blank"
                            rel="noreferrer"
                            style={{ display: 'inline-block', marginTop: '0.5rem', fontSize: '0.8rem' }}
                          >
                            Open audio URL
                          </a>
                        </>
                      )}
                    </div>
                  </div>

                  <div className="container-box" style={{ marginBottom: '1rem' }}>
                    <div
                      style={{
                        fontSize: '0.75rem',
                        fontWeight: 700,
                        color: 'var(--text-muted)',
                        marginBottom: '0.5rem',
                      }}
                    >
                      AI ASSESSMENT
                    </div>
                    <div style={{ fontSize: '0.9rem', marginBottom: '0.35rem' }}>
                      <strong>Confidence:</strong>{' '}
                      {typeof selectedCase.risk_score === 'number'
                        ? `${Math.round(selectedCase.risk_score * 100)}%`
                        : '-'}
                    </div>
                    <div style={{ fontSize: '0.9rem', marginBottom: '0.5rem' }}>
                      <strong>Keywords:</strong>{' '}
                      {Array.isArray(selectedCase.keywords) && selectedCase.keywords.length > 0
                        ? selectedCase.keywords.join(', ')
                        : 'None'}
                    </div>
                    <div style={{ fontSize: '0.95rem', whiteSpace: 'pre-wrap', color: 'var(--text-main)' }}>
                      {getAssessmentText(selectedCase)}
                    </div>
                  </div>

                  {(selectedCase.senior_response || caseReplies.length > 0) && (
                    <div className="container-box" style={{ marginBottom: '1rem' }}>
                      <div
                        style={{
                          fontSize: '0.75rem',
                          fontWeight: 700,
                          color: 'var(--text-muted)',
                          marginBottom: '0.5rem',
                        }}
                      >
                        SENIOR FOLLOW-UP
                      </div>
                      {selectedCase.senior_response && (
                        <div style={{ marginBottom: caseReplies.length > 0 ? '0.75rem' : 0 }}>
                          <div style={{ fontSize: '0.9rem', fontWeight: 700, marginBottom: '0.25rem' }}>
                            Latest English Reply
                          </div>
                          <div style={{ fontStyle: 'italic' }}>
                            "{selectedCase.senior_response}"
                          </div>
                        </div>
                      )}
                      {caseReplies.map((reply, index) => (
                        <div
                          key={`${reply.created_at || 'reply'}-${index}`}
                          style={{
                            marginTop: '0.65rem',
                            paddingTop: '0.65rem',
                            borderTop: '1px solid var(--border)',
                          }}
                        >
                          <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginBottom: '0.3rem' }}>
                            {reply.created_at ? new Date(reply.created_at).toLocaleString() : 'Recent reply'}
                          </div>
                          <div style={{ fontSize: '0.92rem' }}>{reply.english_text || '-'}</div>
                          {reply.translated && reply.original_text && (
                            <div style={{ fontSize: '0.84rem', color: 'var(--text-muted)', marginTop: '0.25rem' }}>
                              Original: {reply.original_text}
                            </div>
                          )}
                          {resolveAudioUrl(reply.audio_url) && (
                            <audio
                              controls
                              src={resolveAudioUrl(reply.audio_url) || undefined}
                              style={{ width: '100%', height: '32px', marginTop: '0.4rem' }}
                            >
                              Your browser does not support the audio element.
                            </audio>
                          )}
                        </div>
                      ))}
                    </div>
                  )}

                  {!isClosedAlert(selectedCase) && (
                    <div
                      className="action-grid"
                      style={{
                        display: 'grid',
                        gridTemplateColumns: '1fr 1fr',
                        gap: '1rem',
                        marginBottom: '1.5rem',
                      }}
                    >
                      <button
                        className="btn-emergency"
                        onClick={() => handleIntervention('ambulance')}
                        disabled={Boolean(selectedCase.ambulance_dispatched || dispatchAmbulanceNow)}
                        style={
                          Boolean(selectedCase.ambulance_dispatched || dispatchAmbulanceNow)
                            ? { opacity: 0.5, cursor: 'not-allowed', background: '#6b7280' }
                            : {}
                        }
                      >
                        {Boolean(selectedCase.ambulance_dispatched || dispatchAmbulanceNow)
                          ? 'AMBULANCE EN ROUTE'
                          : 'DISPATCH AMBULANCE'}
                      </button>
                      <button
                        className="btn-family"
                        onClick={() => handleIntervention('family')}
                        disabled={caseContacts.length === 0 || Boolean(selectedCase.family_called || callFamilyNow)}
                        style={caseContacts.length === 0 ? { opacity: 0.5, cursor: 'not-allowed' } : {}}
                      >
                        FAMILY MEMBER CALLED
                      </button>
                    </div>
                  )}

                  {!isClosedAlert(selectedCase) && dispatchAmbulanceNow && (
                    <div className="container-box" style={{ marginBottom: '1rem' }}>
                      <div style={{ fontSize: '0.8rem', fontWeight: 700, marginBottom: '0.4rem' }}>
                        Dispatch Ambulance Action Time
                      </div>
                      <input
                        className="mini-input"
                        type="datetime-local"
                        value={dispatchActionTime}
                        onChange={(e) => setDispatchActionTime(e.target.value)}
                      />
                    </div>
                  )}

                  {!isClosedAlert(selectedCase) && callFamilyNow && (
                    <div className="container-box" style={{ marginBottom: '1rem' }}>
                      <div style={{ fontSize: '0.8rem', fontWeight: 700, marginBottom: '0.4rem' }}>
                        Family Contact Action Time
                      </div>
                      <input
                        className="mini-input"
                        type="datetime-local"
                        value={familyActionTime}
                        onChange={(e) => setFamilyActionTime(e.target.value)}
                        style={{ marginBottom: '0.65rem' }}
                      />
                      <div style={{ fontSize: '0.8rem', fontWeight: 700, marginBottom: '0.45rem' }}>
                        Which family member did you contact?
                      </div>
                      <div className="pill-wrap">
                        {caseContacts.map((contact) => {
                          const isSelected = selectedFamilyContactIds.includes(contact.id);
                          return (
                            <button
                              key={contact.id}
                              type="button"
                              className={`pill-chip ${isSelected ? 'active' : ''}`}
                              onClick={() => {
                                setSelectedFamilyContactIds((prev) =>
                                  prev.includes(contact.id)
                                    ? prev.filter((id) => id !== contact.id)
                                    : [...prev, contact.id],
                                );
                              }}
                            >
                              {contact.name}
                            </button>
                          );
                        })}
                      </div>
                    </div>
                  )}

                  <div className="mini-row" style={{ marginBottom: '0.75rem' }}>
                    <button
                      className="dashboard-tab-btn"
                      onClick={async () => {
                        try {
                          await addCaseAsFewShotExample(selectedCase, newSeverity);
                          alert('Case added as few-shot example.');
                        } catch (error) {
                          const message =
                            error instanceof Error ? error.message : 'Failed to add case as example';
                          alert(message);
                        }
                      }}
                    >
                      Add This Case As Example
                    </button>
                  </div>

                  {!isClosedAlert(selectedCase) && (
                    <>
                      <hr
                        style={{
                          margin: '1.5rem 0',
                          border: 'none',
                          borderTop: '1px solid var(--border)',
                        }}
                      />
                      <div style={{ marginBottom: '1rem' }}>
                        <label
                          style={{
                            display: 'block',
                            fontWeight: 700,
                            marginBottom: '0.5rem',
                            fontSize: '0.8rem',
                          }}
                        >
                          UPDATE RISK CATEGORIZATION
                        </label>
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
                              outline: 'none',
                            }}
                            value={newSeverity}
                            onChange={(e) => setNewSeverity(e.target.value as RiskLevel)}
                          >
                            <option value="URGENT">URGENT</option>
                            <option value="NON_URGENT">NON-URGENT</option>
                            <option value="UNCERTAIN">UNCERTAIN</option>
                            <option value="FALSE_ALARM">FALSE ALARM</option>
                          </select>
                        </div>
                      </div>

                      <div className="mini-row" style={{ marginTop: '1rem' }}>
                        <button
                          className="action-btn"
                          style={{ flex: 1, padding: '1rem 1.25rem', fontSize: '1rem' }}
                          onClick={handleSave}
                        >
                          SAVE & UPDATE
                        </button>
                        <button
                          className="dashboard-tab-btn"
                          style={{ flex: 1, padding: '1rem 1.25rem', fontSize: '1rem' }}
                          onClick={handleCloseCase}
                        >
                          CLOSE CASE
                        </button>
                      </div>
                    </>
                  )}
                </>
              )}

              {selectedCaseTab === 'family' && (
                <div className="contact-panel" style={{ maxHeight: '55vh', overflowY: 'auto', paddingRight: '0.25rem' }}>
                  {caseContacts.length === 0 ? (
                    <div style={{ textAlign: 'center', padding: '2rem', color: 'var(--text-muted)' }}>
                      No family contacts found for this senior.
                    </div>
                  ) : (
                    caseContacts.map((contact) => (
                      <div key={contact.id} className="contact-item">
                        <div style={{ fontWeight: 700, marginBottom: '0.5rem' }}>{contact.name}</div>
                        <div style={{ fontSize: '0.9rem', marginBottom: '0.25rem' }}>
                          Relationship: {contact.relationship || '-'}
                        </div>
                        <div style={{ fontSize: '0.9rem', marginBottom: '0.25rem' }}>
                          Phone: {contact.phone_number || '-'}
                        </div>
                        <div style={{ fontSize: '0.9rem' }}>
                          Telegram: {contact.telegram_user_id || '-'}
                        </div>
                      </div>
                    ))
                  )}
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default App;
