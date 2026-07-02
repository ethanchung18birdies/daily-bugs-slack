/*
 * Google Apps Script web app for Slack interactive bug alert buttons.
 *
 * Script Properties required:
 * - ISSUE_MEMORY_SPREADSHEET_ID
 * - SLACK_BOT_TOKEN
 * - SLACK_INTERACTION_SECRET
 *
 * Script Properties optional:
 * - SLACK_ALLOWED_TEAM_ID
 * - SLACK_ALLOWED_API_APP_ID
 */

const ISSUE_MEMORY_TAB = "Issue Memory";
const ISSUE_ACTIONS_LOG_TAB = "Issue Actions Log";

const ISSUE_ACTIONS_LOG_HEADERS = [
  "action_id",
  "issue_id",
  "action",
  "acted_at",
  "actor_slack_id",
  "actor_name",
  "previous_status",
  "new_status",
  "slack_channel_id",
  "slack_message_ts",
];

function doPost(e) {
  const props = PropertiesService.getScriptProperties();
  if ((e.parameter.secret || "") !== props.getProperty("SLACK_INTERACTION_SECRET")) {
    return jsonResponse({ ok: false, error: "invalid_secret" });
  }

  const payload = JSON.parse(e.parameter.payload || "{}");
  const validationError = validateSlackPayload(payload, props);
  if (validationError) {
    return jsonResponse({ ok: false, error: validationError });
  }

  const action = (payload.actions || [])[0] || {};
  const issueId = action.value || "";
  const actionId = action.action_id || "";
  const actorId = (payload.user || {}).id || "";
  const actorName = (payload.user || {}).username || (payload.user || {}).name || actorId;
  const actedAt = new Date().toISOString();
  const channelId = ((payload.container || {}).channel_id || (payload.channel || {}).id || "");
  const messageTs = ((payload.container || {}).message_ts || (payload.message || {}).ts || "");

  const spreadsheet = SpreadsheetApp.openById(props.getProperty("ISSUE_MEMORY_SPREADSHEET_ID"));
  const issueSheet = spreadsheet.getSheetByName(ISSUE_MEMORY_TAB);
  if (!issueSheet) {
    return jsonResponse({ ok: false, error: "missing_issue_memory_tab" });
  }

  const issueLookup = findIssue(issueSheet, issueId);
  if (!issueLookup) {
    return jsonResponse({ ok: false, error: "issue_not_found" });
  }

  const previousStatus = getCell(issueLookup, "status");
  const newStatus = actionId === "resolve_issue" ? "Resolved" : "Acknowledged";
  setCell(issueLookup, "status", newStatus);
  setCell(issueLookup, "updated_at", actedAt);
  setCell(issueLookup, "slack_channel_id", channelId);
  setCell(issueLookup, "slack_message_ts", messageTs);

  if (actionId === "resolve_issue") {
    setCell(issueLookup, "resolved_at", actedAt);
    setCell(issueLookup, "resolved_by", actorName);
    setCell(issueLookup, "close_date", actedAt.slice(0, 10));
  } else if (actionId === "acknowledge_issue") {
    setCell(issueLookup, "acknowledged_at", actedAt);
    setCell(issueLookup, "acknowledged_by", actorName);
  } else {
    return jsonResponse({ ok: false, error: "unsupported_action" });
  }

  appendActionLog(spreadsheet, [
    "action-" + Utilities.getUuid(),
    issueId,
    actionId,
    actedAt,
    actorId,
    actorName,
    previousStatus,
    newStatus,
    channelId,
    messageTs,
  ]);

  updateSlackMessage(props.getProperty("SLACK_BOT_TOKEN"), channelId, messageTs, renderSlackPayload(issueLookup));
  return jsonResponse({ ok: true });
}

function validateSlackPayload(payload, props) {
  if (payload.type !== "block_actions") {
    return "unsupported_payload_type";
  }
  const allowedTeamId = props.getProperty("SLACK_ALLOWED_TEAM_ID") || "";
  if (allowedTeamId && ((payload.team || {}).id || "") !== allowedTeamId) {
    return "invalid_team";
  }
  const allowedAppId = props.getProperty("SLACK_ALLOWED_API_APP_ID") || "";
  if (allowedAppId && (payload.api_app_id || "") !== allowedAppId) {
    return "invalid_app";
  }
  return "";
}

function findIssue(sheet, issueId) {
  const values = sheet.getDataRange().getValues();
  if (!values.length) {
    return null;
  }
  const headers = values[0].map(String);
  const issueIdIndex = headers.indexOf("issue_id");
  if (issueIdIndex === -1) {
    return null;
  }
  for (let rowIndex = 1; rowIndex < values.length; rowIndex++) {
    if (String(values[rowIndex][issueIdIndex]) === issueId) {
      return { sheet, headers, values: values[rowIndex], rowNumber: rowIndex + 1 };
    }
  }
  return null;
}

function getCell(issueLookup, header) {
  const index = issueLookup.headers.indexOf(header);
  return index === -1 ? "" : String(issueLookup.values[index] || "");
}

function setCell(issueLookup, header, value) {
  const index = issueLookup.headers.indexOf(header);
  if (index === -1) {
    return;
  }
  issueLookup.sheet.getRange(issueLookup.rowNumber, index + 1).setValue(value);
  issueLookup.values[index] = value;
}

function appendActionLog(spreadsheet, row) {
  let sheet = spreadsheet.getSheetByName(ISSUE_ACTIONS_LOG_TAB);
  if (!sheet) {
    sheet = spreadsheet.insertSheet(ISSUE_ACTIONS_LOG_TAB);
  }
  const existingHeaders = sheet.getRange(1, 1, 1, Math.max(sheet.getLastColumn(), 1)).getValues()[0].filter(String);
  if (!existingHeaders.length) {
    sheet.getRange(1, 1, 1, ISSUE_ACTIONS_LOG_HEADERS.length).setValues([ISSUE_ACTIONS_LOG_HEADERS]);
  }
  sheet.appendRow(row);
}

function renderSlackPayload(issueLookup) {
  const status = getCell(issueLookup, "status");
  const issueId = getCell(issueLookup, "issue_id");
  const summary = getCell(issueLookup, "issue_summary");
  const rollingCount = getCell(issueLookup, "rolling_window_count");
  const newCount = getCell(issueLookup, "new_since_last_alert");
  const firstNoticed = getCell(issueLookup, "first_noticed");
  const latestReport = getCell(issueLookup, "latest_report");
  const platforms = getCell(issueLookup, "platforms") || "Unknown";
  const links = getCell(issueLookup, "helpscout_links").split(/\n+/).filter(Boolean).slice(0, 10);

  const blocks = [
    { type: "header", text: { type: "plain_text", text: "Recurring Bug Alert", emoji: true } },
    {
      type: "section",
      fields: [
        { type: "mrkdwn", text: "*Status:*\n" + escapeMrkdwn(status) },
        { type: "mrkdwn", text: "*Issue ID:*\n" + escapeMrkdwn(issueId) },
      ],
    },
    { type: "section", text: { type: "mrkdwn", text: "*Issue Summary:*\n" + escapeMrkdwn(summary) } },
    {
      type: "section",
      fields: [
        { type: "mrkdwn", text: "*Report Volume:*\n" + rollingCount + " in window\n" + newCount + " new since last update" },
        { type: "mrkdwn", text: "*Dates:*\nFirst: " + firstNoticed + "\nLatest: " + latestReport },
      ],
    },
    { type: "section", text: { type: "mrkdwn", text: "*Platforms:*\n" + escapeMrkdwn(platforms) } },
    { type: "section", text: { type: "mrkdwn", text: "*Help Scout Links:*\n" + formatLinks(links) } },
  ];

  if (status !== "Resolved") {
    blocks.push({
      type: "actions",
      block_id: "issue_actions__" + issueId,
      elements: [
        { type: "button", action_id: "acknowledge_issue", text: { type: "plain_text", text: "Acknowledge", emoji: true }, value: issueId },
        { type: "button", action_id: "resolve_issue", text: { type: "plain_text", text: "Resolve", emoji: true }, style: "primary", value: issueId },
      ],
    });
  }

  return {
    text: status + ": " + summary + " (" + rollingCount + " reports)",
    blocks,
    unfurl_links: false,
    unfurl_media: false,
  };
}

function updateSlackMessage(botToken, channelId, messageTs, payload) {
  const response = UrlFetchApp.fetch("https://slack.com/api/chat.update", {
    method: "post",
    contentType: "application/json; charset=utf-8",
    headers: { Authorization: "Bearer " + botToken },
    payload: JSON.stringify(Object.assign({ channel: channelId, ts: messageTs }, payload)),
    muteHttpExceptions: true,
  });
  const body = JSON.parse(response.getContentText() || "{}");
  if (!body.ok) {
    throw new Error("Slack chat.update failed: " + (body.error || "unknown_error"));
  }
}

function formatLinks(links) {
  if (!links.length) {
    return "No Help Scout links found";
  }
  return links.map(function(link) {
    return "* <" + link.replace(/\|/g, "%7C") + "|" + link + ">";
  }).join("\n");
}

function escapeMrkdwn(value) {
  return String(value || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function jsonResponse(value) {
  return ContentService.createTextOutput(JSON.stringify(value)).setMimeType(ContentService.MimeType.JSON);
}
