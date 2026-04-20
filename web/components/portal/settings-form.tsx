"use client";

import { useState, useTransition } from "react";
import { Notice } from "@/components/portal/notice";
import { Panel } from "@/components/portal/panel";
import { StatusBadge, statusTone } from "@/components/portal/status-badge";
import {
  sanitizeSupportEmail,
  sanitizeTenantName,
  sanitizeWebsiteUrl,
} from "@/lib/tenant-display";
import { isPreviewAuthMode } from "@/lib/clerk-env";
import { useBrowserApi } from "@/services/api/browser";
import { ApiError } from "@/services/api/shared";
import type { MeResponse, TenantResponse } from "@/services/api/types";

function errorMessage(error: unknown, fallback: string) {
  if (error instanceof ApiError && error.detail) {
    return error.detail;
  }
  if (error instanceof Error && error.message) {
    return error.message;
  }
  return fallback;
}

export function SettingsForm({
  me,
  tenant,
  showBillingRequired,
}: {
  me: MeResponse;
  tenant: TenantResponse;
  showBillingRequired?: boolean;
}) {
  const api = useBrowserApi();
  const [isPending, startTransition] = useTransition();
  const [feedback, setFeedback] = useState<{ tone: "success" | "error"; text: string } | null>(null);
  const [companyName, setCompanyName] = useState(sanitizeTenantName(tenant.tenantName) ?? "");
  const [websiteUrl, setWebsiteUrl] = useState(sanitizeWebsiteUrl(tenant.websiteUrl) ?? "");
  const [supportEmail, setSupportEmail] = useState(sanitizeSupportEmail(tenant.supportEmail) ?? "");
  const [industry, setIndustry] = useState(tenant.industry ?? "");
  const [confidenceThreshold, setConfidenceThreshold] = useState(
    typeof tenant.settings.confidenceThreshold === "number" ? tenant.settings.confidenceThreshold : 0.75,
  );
  const previewAuth = isPreviewAuthMode();
  const gatewayBilling = process.env.NEXT_PUBLIC_BILLING_MODE?.trim().toLowerCase() === "stripe";

  function saveSettings() {
    setFeedback(null);
    startTransition(async () => {
      try {
        await api.saveTenant({
          tenantName: companyName,
          websiteUrl,
          supportEmail,
          industry,
          settings: {
            confidenceThreshold,
          },
        });
        setFeedback({ tone: "success", text: "Settings saved." });
      } catch (error) {
        setFeedback({
          tone: "error",
          text: errorMessage(error, "Unable to save tenant settings."),
        });
      }
    });
  }

  function goToCheckout() {
    setFeedback(null);
    startTransition(async () => {
      try {
        const session = await api.createCheckoutSession();
        if (session.url) {
          window.location.href = session.url;
          return;
        }
        setFeedback({ tone: "error", text: "Payment checkout did not return a redirect URL." });
      } catch (error) {
        setFeedback({
          tone: "error",
          text: errorMessage(error, "Unable to open payment checkout."),
        });
      }
    });
  }

  function goToBillingPortal() {
    setFeedback(null);
    startTransition(async () => {
      try {
        const session = await api.createPortalSession();
        if (session.url) {
          window.location.href = session.url;
          return;
        }
        setFeedback({ tone: "error", text: "Payment billing portal did not return a redirect URL." });
      } catch (error) {
        setFeedback({
          tone: "error",
          text: errorMessage(error, "Unable to open the billing portal."),
        });
      }
    });
  }

  const inactive = !me.hasActiveSubscription;

  return (
    <div className="grid gap-6 xl:grid-cols-[1fr_0.9fr]">
      <div className="space-y-6">
        {showBillingRequired ? (
          <Notice
            title="Manual approval required"
            copy="Operational pages stay locked until SVMP marks this tenant as active or trialing after manual payment acceptance."
            tone="warning"
          />
        ) : null}

        <Panel
          title="Business profile"
          eyebrow={tenant.tenantId}
          action={
            <button
              type="button"
              className="rounded-[8px] bg-ink px-4 py-3 text-sm font-semibold text-paper hover:bg-pine disabled:cursor-not-allowed disabled:opacity-60"
              onClick={saveSettings}
              disabled={isPending || inactive}
            >
              {isPending ? "Saving..." : "Save settings"}
            </button>
          }
        >
          <div className="grid gap-4 md:grid-cols-2">
            <label className="grid gap-2">
              <span className="text-sm font-semibold">Company name</span>
              <input
                className="h-11 rounded-[8px] border border-line bg-paper px-3 text-sm outline-none focus:border-pine"
                value={companyName}
                onChange={(event) => setCompanyName(event.target.value)}
                disabled={inactive}
              />
            </label>
            <label className="grid gap-2">
              <span className="text-sm font-semibold">Website</span>
              <input
                className="h-11 rounded-[8px] border border-line bg-paper px-3 text-sm outline-none focus:border-pine"
                value={websiteUrl}
                onChange={(event) => setWebsiteUrl(event.target.value)}
                disabled={inactive}
              />
            </label>
            <label className="grid gap-2">
              <span className="text-sm font-semibold">Support email</span>
              <input
                className="h-11 rounded-[8px] border border-line bg-paper px-3 text-sm outline-none focus:border-pine"
                value={supportEmail}
                onChange={(event) => setSupportEmail(event.target.value)}
                disabled={inactive}
              />
            </label>
            <label className="grid gap-2">
              <span className="text-sm font-semibold">Industry</span>
              <input
                className="h-11 rounded-[8px] border border-line bg-paper px-3 text-sm outline-none focus:border-pine"
                value={industry}
                onChange={(event) => setIndustry(event.target.value)}
                disabled={inactive}
              />
            </label>
          </div>
          {feedback ? (
            <div className="mt-4">
              <Notice
                title={feedback.tone === "success" ? "Saved" : "Needs attention"}
                copy={feedback.text}
                tone={feedback.tone}
              />
            </div>
          ) : null}
        </Panel>

        <Panel title="Tenant access" eyebrow="Verified user">
          <div className="space-y-4">
            <p className="text-sm leading-6 text-ink/62">
              {previewAuth
                ? "Preview mode is using built-in access so the portal can be reviewed without Clerk."
                : "Clerk verifies identity. MongoDB decides the tenant, role, and permissions for this user."}
            </p>
            <div className="rounded-[8px] border border-line bg-paper p-4 text-sm leading-6 text-ink/64">
              Access scope: {me.organizationId}
            </div>
            <div className="rounded-[8px] border border-line bg-paper p-4 text-sm leading-6 text-ink/64">
              Role: {me.role}. Tenant: {me.tenantId}.
            </div>
          </div>
        </Panel>
      </div>

      <div className="space-y-6">
        <Panel title="Billing" eyebrow="Subscription">
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-[8px] border border-line bg-paper p-4">
            <div>
              <p className="font-semibold">Paid access</p>
              <p className="mt-2 text-sm text-ink/60">
                {inactive
                  ? "This workspace is inactive until SVMP manually approves paid access."
                  : "Paid access is active for this tenant."}
              </p>
            </div>
            <StatusBadge tone={statusTone(tenant.billing.status)}>{tenant.billing.status}</StatusBadge>
          </div>
          {gatewayBilling ? (
            <div className="mt-4 flex flex-wrap gap-2">
              <button
                type="button"
                className="rounded-[8px] bg-ink px-4 py-3 text-sm font-semibold text-paper hover:bg-pine disabled:cursor-not-allowed disabled:opacity-60"
                onClick={goToCheckout}
                disabled={isPending}
              >
                Open checkout
              </button>
              <button
                type="button"
                className="rounded-[8px] border border-line bg-white px-4 py-3 text-sm font-semibold hover:border-ink disabled:cursor-not-allowed disabled:opacity-60"
                onClick={goToBillingPortal}
                disabled={isPending}
              >
                Open billing portal
              </button>
            </div>
          ) : (
            <div className="mt-4 rounded-[8px] border border-line bg-paper p-4 text-sm leading-6 text-ink/64">
              Pilot billing is handled manually. After payment is accepted, set this tenant's subscription status to
              active or trialing in MongoDB.
            </div>
          )}
        </Panel>

        <Panel title="API and webhooks" eyebrow="Endpoints">
          <div className="space-y-3 text-sm">
            <div>
              <p className="font-semibold">Dashboard API</p>
              <p className="mt-2 break-all rounded-[8px] bg-mist px-3 py-2 text-ink/68">
                https://api.svmpsystems.com/api
              </p>
            </div>
            <div>
              <p className="font-semibold">WhatsApp webhook</p>
              <p className="mt-2 break-all rounded-[8px] bg-mist px-3 py-2 text-ink/68">
                https://api.svmpsystems.com/webhook
              </p>
            </div>
            {gatewayBilling ? (
              <div>
                <p className="font-semibold">Payment webhook</p>
                <p className="mt-2 break-all rounded-[8px] bg-mist px-3 py-2 text-ink/68">
                  https://api.svmpsystems.com/api/billing/webhook
                </p>
              </div>
            ) : null}
          </div>
        </Panel>

        <Panel title="Automation controls" eyebrow="Runtime settings">
          <label className="grid gap-2">
            <span className="text-sm font-semibold">Confidence threshold</span>
            <input
              type="number"
              min="0"
              max="1"
              step="0.01"
              className="h-11 rounded-[8px] border border-line bg-paper px-3 text-sm outline-none focus:border-pine"
              value={confidenceThreshold}
              onChange={(event) => setConfidenceThreshold(Number(event.target.value))}
              disabled={inactive}
            />
          </label>
          <div className="mt-4 rounded-[8px] border border-line bg-paper p-4">
            <p className="font-semibold">Auto-answering</p>
            <p className="mt-2 text-sm leading-6 text-ink/62">
              Answers below threshold escalate automatically. Provider credentials stay server-side.
            </p>
          </div>
        </Panel>
      </div>
    </div>
  );
}
