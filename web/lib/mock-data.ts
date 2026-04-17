export type Role = "owner" | "admin" | "analyst" | "viewer";

export type Metric = {
  label: string;
  value: string;
  detail: string;
  trend: string;
};

export type Session = {
  id: string;
  customer: string;
  provider: string;
  status: "resolved" | "escalated" | "pending" | "failed";
  question: string;
  answer: string | null;
  source: string | null;
  confidence: number | null;
  safety: number | null;
  escalationReason: string | null;
  timestamp: string;
  transcript: Array<{
    speaker: "customer" | "svmp" | "human";
    text: string;
    at: string;
  }>;
};

export type KnowledgeEntry = {
  id: string;
  topic: string;
  question: string;
  answer: string;
  active: boolean;
  updatedAt: string;
  tags: string[];
};

export type GovernanceLog = {
  id: string;
  decision: "answered" | "escalated" | "blocked";
  question: string;
  reason: string;
  source: string | null;
  similarity: number | null;
  groundedness: number | null;
  safety: number | null;
  timestamp: string;
};

export type Integration = {
  provider: "whatsapp" | "slack" | "shopify" | "zendesk";
  title: string;
  status: "connected" | "not_connected" | "coming_soon";
  health: "healthy" | "warning" | "unknown";
  detail: string;
  lastSync: string | null;
};

export const tenant = {
  tenantId: "stay",
  tenantName: "Stay Parfums",
  websiteUrl: "https://stayparfums.com",
  supportEmail: "support@stayparfums.com",
  role: "owner" as Role,
  subscriptionStatus: "active",
  confidenceThreshold: 0.75,
  onboardingStatus: "completed",
};

export const metrics: Metric[] = [
  {
    label: "Deflection rate",
    value: "68%",
    detail: "Simple questions handled without a human reply.",
    trend: "+9% this week",
  },
  {
    label: "Human hours saved",
    value: "42.5",
    detail: "Estimated time saved across WhatsApp support.",
    trend: "+6.2 hours",
  },
  {
    label: "Avg. resolution",
    value: "1m 18s",
    detail: "Median time from first message to outcome.",
    trend: "22s faster",
  },
  {
    label: "Safety score",
    value: "96",
    detail: "Grounded answers, escalations, and blocked responses.",
    trend: "Stable",
  },
];

export const automationTrend = [
  { day: "Mon", answered: 42, escalated: 11 },
  { day: "Tue", answered: 51, escalated: 14 },
  { day: "Wed", answered: 48, escalated: 10 },
  { day: "Thu", answered: 57, escalated: 12 },
  { day: "Fri", answered: 63, escalated: 15 },
  { day: "Sat", answered: 35, escalated: 8 },
  { day: "Sun", answered: 31, escalated: 7 },
];

export const topicDistribution = [
  { name: "Shipping", value: 31 },
  { name: "Pricing", value: 24 },
  { name: "Fragrance choice", value: 19 },
  { name: "Returns", value: 14 },
  { name: "Stock", value: 12 },
];

export const responseByHour = [
  { hour: "9a", minutes: 2.1 },
  { hour: "11a", minutes: 1.4 },
  { hour: "1p", minutes: 1.1 },
  { hour: "3p", minutes: 1.3 },
  { hour: "5p", minutes: 1.8 },
  { hour: "7p", minutes: 2.4 },
];

export const sessions: Session[] = [
  {
    id: "sess_1001",
    customer: "+91 98458 91194",
    provider: "WhatsApp Meta",
    status: "resolved",
    question: "Do you have free shipping for the discovery set?",
    answer: "Yes, free shipping is available on eligible orders. The discovery set page shows the final shipping status at checkout.",
    source: "FAQ shipping policy",
    confidence: 0.92,
    safety: 0.98,
    escalationReason: null,
    timestamp: "Today, 10:42 AM",
    transcript: [
      { speaker: "customer", text: "Hi, do you have free shipping?", at: "10:41 AM" },
      { speaker: "customer", text: "For the discovery set", at: "10:42 AM" },
      { speaker: "svmp", text: "Yes, free shipping is available on eligible orders. The discovery set page shows the final shipping status at checkout.", at: "10:42 AM" },
    ],
  },
  {
    id: "sess_1002",
    customer: "+91 99450 11220",
    provider: "WhatsApp Twilio",
    status: "escalated",
    question: "Can I mix two offers with a custom bottle engraving?",
    answer: null,
    source: "FAQ promotions",
    confidence: 0.48,
    safety: 0.91,
    escalationReason: "Offer stacking and custom engraving were not covered by approved knowledge.",
    timestamp: "Today, 9:18 AM",
    transcript: [
      { speaker: "customer", text: "Can I mix two offers?", at: "9:17 AM" },
      { speaker: "customer", text: "Also want engraving", at: "9:18 AM" },
      { speaker: "human", text: "Escalated for support follow-up.", at: "9:18 AM" },
    ],
  },
  {
    id: "sess_1003",
    customer: "+91 90080 33445",
    provider: "WhatsApp Meta",
    status: "pending",
    question: "Is Ocean available in 100 ml?",
    answer: null,
    source: null,
    confidence: null,
    safety: null,
    escalationReason: null,
    timestamp: "Yesterday, 6:02 PM",
    transcript: [
      { speaker: "customer", text: "Is Ocean available in 100 ml?", at: "6:02 PM" },
    ],
  },
  {
    id: "sess_1004",
    customer: "+91 98110 66880",
    provider: "WhatsApp Meta",
    status: "resolved",
    question: "What is your return window?",
    answer: "Returns are accepted according to the policy on the store. SVMP can share the policy summary and escalate order-specific cases.",
    source: "FAQ returns",
    confidence: 0.87,
    safety: 0.95,
    escalationReason: null,
    timestamp: "Yesterday, 4:44 PM",
    transcript: [
      { speaker: "customer", text: "What is your return window?", at: "4:43 PM" },
      { speaker: "svmp", text: "Returns are accepted according to the policy on the store. SVMP can share the policy summary and escalate order-specific cases.", at: "4:44 PM" },
    ],
  },
];

export const knowledgeEntries: KnowledgeEntry[] = [
  {
    id: "faq_shipping_free",
    topic: "Shipping",
    question: "Do you offer free shipping?",
    answer: "Free shipping is available on eligible orders. Customers should confirm the final shipping status at checkout.",
    active: true,
    updatedAt: "Apr 17, 2026",
    tags: ["shipping", "checkout"],
  },
  {
    id: "faq_returns",
    topic: "Returns",
    question: "What is your return window?",
    answer: "Returns follow the policy shown on the store. Order-specific questions should be escalated to support.",
    active: true,
    updatedAt: "Apr 16, 2026",
    tags: ["returns", "policy"],
  },
  {
    id: "faq_pair_offer",
    topic: "Pricing",
    question: "What is the pair offer?",
    answer: "Any two eligible fragrances can be purchased together under the current pair offer when the promotion is active.",
    active: true,
    updatedAt: "Apr 14, 2026",
    tags: ["offer", "pricing"],
  },
  {
    id: "faq_old_discount",
    topic: "Pricing",
    question: "Do you still have the launch discount?",
    answer: "The launch discount is no longer active.",
    active: false,
    updatedAt: "Mar 29, 2026",
    tags: ["discount"],
  },
];

export const governanceLogs: GovernanceLog[] = [
  {
    id: "gov_001",
    decision: "answered",
    question: "Do you have free shipping for the discovery set?",
    reason: "Score met threshold and answer was grounded in FAQ shipping policy.",
    source: "FAQ shipping policy",
    similarity: 0.92,
    groundedness: 0.97,
    safety: 0.98,
    timestamp: "Today, 10:42 AM",
  },
  {
    id: "gov_002",
    decision: "escalated",
    question: "Can I mix two offers with engraving?",
    reason: "Policy combination was not covered by approved knowledge.",
    source: "FAQ promotions",
    similarity: 0.48,
    groundedness: 0.64,
    safety: 0.91,
    timestamp: "Today, 9:18 AM",
  },
  {
    id: "gov_003",
    decision: "blocked",
    question: "Guarantee this will last forever?",
    reason: "Overpromising claim blocked by brand and safety rules.",
    source: null,
    similarity: null,
    groundedness: null,
    safety: 0.22,
    timestamp: "Yesterday, 7:31 PM",
  },
];

export const integrations: Integration[] = [
  {
    provider: "whatsapp",
    title: "WhatsApp",
    status: "connected",
    health: "healthy",
    detail: "Meta webhook verified. Last inbound event processed successfully.",
    lastSync: "5 minutes ago",
  },
  {
    provider: "slack",
    title: "Slack",
    status: "coming_soon",
    health: "unknown",
    detail: "Support handoff destination for future internal alerts.",
    lastSync: null,
  },
  {
    provider: "shopify",
    title: "Shopify",
    status: "coming_soon",
    health: "unknown",
    detail: "Product and order context for future support workflows.",
    lastSync: null,
  },
  {
    provider: "zendesk",
    title: "Zendesk",
    status: "coming_soon",
    health: "unknown",
    detail: "Ticket handoff and conversation export for later releases.",
    lastSync: null,
  },
];

export const auditEvents = [
  {
    action: "knowledge_base.updated",
    actor: "owner@stayparfums.com",
    detail: "Updated free shipping answer",
    timestamp: "Today, 10:05 AM",
  },
  {
    action: "brand_voice.updated",
    actor: "admin@stayparfums.com",
    detail: "Added words to avoid",
    timestamp: "Yesterday, 5:22 PM",
  },
  {
    action: "integration.whatsapp.updated",
    actor: "owner@stayparfums.com",
    detail: "Marked Meta webhook healthy",
    timestamp: "Apr 15, 2026",
  },
];
