import React, { useState, useEffect, useCallback, useRef } from "react";
import {
  Alert,
  Box,
  Typography,
  Button,
  Card,
  CardContent,
  Chip,
  CircularProgress,
  Dialog,
  DialogContent,
  Divider,
  IconButton,
  LinearProgress,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
} from "@mui/material";
import CloseIcon from "@mui/icons-material/Close";
import LinkIcon from "@mui/icons-material/Link";
import CloudUploadIcon from "@mui/icons-material/CloudUpload";
import CheckCircleIcon from "@mui/icons-material/CheckCircle";
import HourglassEmptyIcon from "@mui/icons-material/HourglassEmpty";
import {
  listManagers,
  listOffices,
  listTickets,
  listTicketAssignments,
  listTicketAnalyses,
  listAnalysisMeta,
  listTicketsWithAttachments,
  listAttachments,
  uploadFileToS3,
  createAttachment,
  createAttachmentType,
  listAttachmentTypes,
  addAttachmentsToTicket,
  triggerAnalyzeFromDb,
  triggerRoutingFromDb,
} from "../api/backendCrud";

const getUrgencyColor = (score) => {
  const num = parseInt(score, 10);
  if (!num || num < 1) return "#6b7280";
  // 1=green → 10=red, smooth gradient
  const colors = [
    "#16a34a", // 1  green
    "#22c55e", // 2
    "#65a30d", // 3  lime
    "#a3e635", // 4
    "#d97706", // 5  amber
    "#ea580c", // 6  orange
    "#f97316", // 7
    "#ef4444", // 8  red-400
    "#dc2626", // 9  red-600
    "#991b1b", // 10 red-800
  ];
  return colors[Math.min(num, 10) - 1] || "#6b7280";
};

const sentimentColors = {
  // English
  positive: "#16a34a", neutral: "#6b7280", negative: "#dc2626", mixed: "#d97706",
  // Russian
  "позитивный": "#16a34a", "нейтральный": "#6b7280", "негативный": "#dc2626", "смешанный": "#d97706",
};

const UrgencyChip = ({ value }) => {
  if (!value || value === "-") return <span>-</span>;
  const color = getUrgencyColor(value);
  return <Chip label={value} size="small" sx={{ bgcolor: color, color: "#fff", fontWeight: 700, "& .MuiChip-label": { color: "#fff" } }} />;
};

const SentimentChip = ({ value }) => {
  if (!value || value === "-") return <span>-</span>;
  const color = sentimentColors[String(value).toLowerCase()] || "#6b7280";
  return <Chip label={value} size="small" sx={{ bgcolor: color, color: "#fff", fontWeight: 600, "& .MuiChip-label": { color: "#fff" } }} />;
};

const DashboardPage = ({ onBack }) => {
  const [managers, setManagers] = useState([]);
  const [tickets, setTickets] = useState([]);
  const [analyses, setAnalyses] = useState([]);
  const [analysisMeta, setAnalysisMeta] = useState([]);
  const [businessUnits, setBusinessUnits] = useState([]);
  const [assignments, setAssignments] = useState([]);
  const [view, setView] = useState("load");
  const [loading, setLoading] = useState(false);
  const [ticketSortOrder, setTicketSortOrder] = useState("none"); // "none" | "asc" | "desc"
  const [backendError, setBackendError] = useState("");
  const [actionStatus, setActionStatus] = useState(""); // "", "analyzing", "routing", "done"
  const [actionError, setActionError] = useState("");
  const [loadMode, setLoadMode] = useState("before");
  const [attachmentsList, setAttachmentsList] = useState([]);
  const [ticketsWithAttachments, setTicketsWithAttachments] = useState([]);
  const [uploadingImage, setUploadingImage] = useState(false);
  const [uploadError, setUploadError] = useState("");
  const [lightboxUrl, setLightboxUrl] = useState(null);
  const fileInputRef = useRef(null);
  const manualSyncInputRef = useRef(null);
  const [uploadTargetTicketId, setUploadTargetTicketId] = useState(null);
  const [manualSyncTarget, setManualSyncTarget] = useState(null); // { s3Key, attId }

  const fetchData = useCallback(async () => {
    setLoading(true);
    setBackendError("");
    const [managersResult, ticketsResult, officesResult, assignResult, analysisResult] =
      await Promise.allSettled([
        listManagers({ expand_position: true, expand_city: true, expand_skills: true }),
        listTickets({
          expand: true,
          include_attachments: false,
          include_attachment_type: false,
          include_attachment_url: false,
        }),
        listOffices({ expand_city: true }),
        listTicketAssignments(),
        listTicketAnalyses(),
      ]);

    // Fetch attachments (non-blocking)
    let attachResult = [];
    let ticketsAttResult = [];
    let metaResult = [];
    try {
      [attachResult, ticketsAttResult, metaResult] = await Promise.all([
        listAttachments(),
        listTicketsWithAttachments(),
        listAnalysisMeta(true),
      ]);
    } catch (_e) { /* ignore if endpoints fail */ }

    const errors = [];

    if (managersResult.status === "fulfilled") {
      setManagers(managersResult.value || []);
    } else {
      errors.push(`Managers: ${managersResult.reason?.message || "request failed"}`);
      setManagers([]);
    }

    if (ticketsResult.status === "fulfilled") {
      setTickets(ticketsResult.value || []);
    } else {
      errors.push(`Tickets: ${ticketsResult.reason?.message || "request failed"}`);
      setTickets([]);
    }

    if (officesResult.status === "fulfilled") {
      setBusinessUnits(officesResult.value || []);
    } else {
      errors.push(`Business Units: ${officesResult.reason?.message || "request failed"}`);
      setBusinessUnits([]);
    }

    if (assignResult.status === "fulfilled") {
      setAssignments(assignResult.value || []);
    } else {
      setAssignments([]);
    }

    if (analysisResult.status === "fulfilled") {
      setAnalyses(analysisResult.value || []);
    } else {
      setAnalyses([]);
    }

    setAttachmentsList(Array.isArray(attachResult) ? attachResult : []);
    setTicketsWithAttachments(Array.isArray(ticketsAttResult) ? ticketsAttResult : []);
    setAnalysisMeta(Array.isArray(metaResult) ? metaResult : []);

    if (errors.length) {
      setBackendError(errors.join(" | "));
    }

    setLoading(false);
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handleRefresh = async () => {
    await fetchData();
  };

  const handleRunAnalysis = async () => {
    setActionStatus("analyzing");
    setActionError("");
    try {
      await triggerAnalyzeFromDb();
      setActionStatus("done");
      await fetchData();
    } catch (err) {
      setActionError(`Analysis failed: ${err.message}`);
      setActionStatus("");
    }
  };

  const handleRunRouting = async () => {
    setActionStatus("routing");
    setActionError("");
    try {
      await triggerRoutingFromDb();
      setActionStatus("done");
      await fetchData();
    } catch (err) {
      setActionError(`Routing failed: ${err.message}`);
      setActionStatus("");
    }
  };

  // ── Image upload handler with auto-sync by CSV filename ─────────────
  const handleImageUpload = async (e) => {
    const files = Array.from(e.target.files || []);
    e.target.value = "";
    if (!files.length) return;

    setUploadingImage(true);
    setUploadError("");

    try {
      // Ensure image/* attachment type exists
      let attTypes = [];
      try { attTypes = await listAttachmentTypes(); } catch (_) {}

      const ensureType = async (mime) => {
        const found = attTypes.find((t) => t.name?.toLowerCase() === mime.toLowerCase());
        if (found) return found.id_;
        const created = await createAttachmentType({ name: mime });
        attTypes.push(created);
        return created.id_;
      };

      // Build a filename → attachment record index for auto-sync
      // attachmentsList records created from CSV have keys like "tickets/<tid>/<filename>"
      const filenameToRecord = {};
      attachmentsList.forEach((att) => {
        const key = att.key || "";
        const fname = key.split("/").pop()?.toLowerCase();
        if (fname) {
          if (!filenameToRecord[fname]) filenameToRecord[fname] = [];
          filenameToRecord[fname].push(att);
        }
      });

      // Build ticket attachment lookup: attachment key → ticket id
      const keyToTicketId = {};
      ticketsWithAttachments.forEach((t) => {
        const tid = t.id_ || t.id;
        (t.attachments || []).forEach((a) => {
          if (a.key) keyToTicketId[a.key] = tid;
        });
      });

      const syncResults = [];

      for (const file of files) {
        const mime = file.type || "application/octet-stream";
        const typeId = await ensureType(mime);
        const lowerName = file.name.toLowerCase();

        // Check if this filename matches an existing attachment record from CSV
        const matchedRecords = filenameToRecord[lowerName] || [];

        if (matchedRecords.length > 0) {
          // Auto-sync: upload to each matching S3 key
          for (const rec of matchedRecords) {
            await uploadFileToS3(file, rec.key, "static");
            const tid = keyToTicketId[rec.key];
            syncResults.push({ file: file.name, key: rec.key, ticketId: tid, autoSynced: true });
          }
        } else if (uploadTargetTicketId) {
          // Manual link to a specific ticket
          const s3Key = `tickets/${uploadTargetTicketId}/${file.name}`;
          await uploadFileToS3(file, s3Key, "static");
          const att = await createAttachment({ type_id: typeId, key: s3Key });
          if (att.id_) {
            try {
              await addAttachmentsToTicket(uploadTargetTicketId, [att.id_]);
            } catch (_) { /* non-fatal */ }
          }
          syncResults.push({ file: file.name, key: s3Key, ticketId: uploadTargetTicketId, autoSynced: false });
        } else {
          // No match, no target — upload as unlinked
          const s3Key = `uploads/${file.name}`;
          await uploadFileToS3(file, s3Key, "static");
          await createAttachment({ type_id: typeId, key: s3Key });
          syncResults.push({ file: file.name, key: s3Key, ticketId: null, autoSynced: false });
        }
      }

      const synced = syncResults.filter((r) => r.autoSynced).length;
      if (synced > 0) {
        setUploadError(""); // clear previous
        setActionStatus("done");
      }
      await fetchData();
    } catch (err) {
      setUploadError(`Image upload failed: ${err.message}`);
    } finally {
      setUploadingImage(false);
      setUploadTargetTicketId(null);
    }
  };

  // ── Manual sync handler: upload file to a specific S3 key ──────────
  const handleManualSync = async (e) => {
    const files = Array.from(e.target.files || []);
    e.target.value = "";
    if (!files.length || !manualSyncTarget) return;

    setUploadingImage(true);
    setUploadError("");

    try {
      for (const file of files) {
        await uploadFileToS3(file, manualSyncTarget.s3Key, "static");
      }
      await fetchData();
    } catch (err) {
      setUploadError(`Manual sync failed: ${err.message}`);
    } finally {
      setUploadingImage(false);
      setManualSyncTarget(null);
    }
  };

  const getLoadColor = (load, maxVal) => {
    const pct = maxVal > 0 ? (load / maxVal) * 100 : 0;
    if (pct >= 70) return "#f44336";
    if (pct >= 35) return "#ffeb3b";
    return "#4caf50";
  };

  const sidebarButtonSx = (isActive) => ({
    mb: 1.2,
    minHeight: 52,
    borderRadius: 3,
    fontSize: "1rem",
    letterSpacing: "0.02em",
    borderWidth: "2px",
    color: isActive ? "#ffffff" : "#0f172a",
    borderColor: isActive ? "transparent" : "rgba(15, 23, 42, 0.18)",
    background: isActive
      ? "linear-gradient(120deg, #0ea5e9 0%, #2563eb 50%, #7c3aed 100%)"
      : "linear-gradient(120deg, rgba(255,255,255,0.95) 0%, rgba(241,245,249,0.92) 100%)",
    transform: isActive ? "scale(1.08)" : "scale(1)",
    transformOrigin: "center",
    transition: "transform 160ms ease, box-shadow 160ms ease, background 220ms ease",
    fontWeight: isActive ? 700 : 500,
    boxShadow: isActive ? "0 10px 24px rgba(37, 99, 235, 0.35)" : "0 2px 8px rgba(15, 23, 42, 0.10)",
    "&:hover": {
      transform: "scale(1.08)",
      boxShadow: "0 10px 24px rgba(37, 99, 235, 0.28)",
      background: isActive
        ? "linear-gradient(120deg, #0284c7 0%, #1d4ed8 50%, #6d28d9 100%)"
        : "linear-gradient(120deg, rgba(255,255,255,1) 0%, rgba(226,232,240,0.95) 100%)",
    },
  });

  // Count assignments per manager for before/after comparison
  const assignmentCountByManager = {};
  assignments.forEach((a) => {
    assignmentCountByManager[a.manager_id] = (assignmentCountByManager[a.manager_id] || 0) + 1;
  });

  const managerLoadRows = managers.map((manager, index) => {
    const baseLoad = Number(manager.in_progress_requests || 0);
    const assignedCount = assignmentCountByManager[manager.id_] || 0;
    const rawLoad = loadMode === "after" ? baseLoad + assignedCount : baseLoad;
    const displayLoad = Number.isFinite(rawLoad) ? rawLoad : 0;
    return {
      managerIndex: manager.id_ || index + 1,
      load: displayLoad,
      displayLoad,
    };
  });

  const rawMax = Math.max(...managerLoadRows.map((r) => r.displayLoad), 0);
  const maxLoad = Math.max(10, rawMax + 3);

  const managerTableRows = managers.map((manager) => ({
    id: manager.id_,
    name: `Менеджер ${manager.id_}`,
    position: manager.position?.name || manager.position_id || "-",
    city: manager.city?.name || manager.city_id || "-",
    skills: (manager.skills || []).map((skill) => skill.name).join(", ") || "-",
    inProgress: manager.in_progress_requests ?? 0,
  }));

  // Build analysis lookup: ticket_id → analysis object
  const analysisMap = {};
  analyses.forEach((a) => {
    analysisMap[a.ticket_id] = a;
  });

  // Build ticket → attachment count map
  const ticketAttachmentCount = {};
  ticketsWithAttachments.forEach((t) => {
    const tid = t.id_ || t.id;
    const count = (t.attachments || []).length;
    if (count > 0) ticketAttachmentCount[tid] = count;
  });

  const ticketTableRows = tickets.map((ticket) => {
    const addressText = ticket.address
      ? `${ticket.address.street || ""} ${ticket.address.home_number || ""}`.trim()
      : "-";
    const analysis = analysisMap[ticket.id_] || {};
    return {
      id: ticket.id_,
      segment: ticket.segment?.name || ticket.segment_id || "-",
      gender: ticket.gender?.name || ticket.gender_id || "-",
      dateOfBirth: ticket.date_of_birth || "-",
      address: addressText || "-",
      description: (ticket.description || "-").slice(0, 80),
      urgency: analysis.urgency_score || "-",
      sentiment: analysis.sentiment || "-",
      requestType: analysis.request_type || "-",
      language: analysis.language || "-",
      summary: analysis.summary || "-",
      attachmentCount: ticketAttachmentCount[ticket.id_] || 0,
    };
  });

  // Build assignment lookup: ticket_id → assignment
  const assignmentMap = {};
  assignments.forEach((a) => {
    assignmentMap[a.ticket_id] = a;
  });

  const assignmentRows = assignments.map((a) => {
    const ticket = tickets.find((t) => t.id_ === a.ticket_id);
    const manager = managers.find((m) => m.id_ === a.manager_id);
    return {
      ticketId: a.ticket_id,
      ticketDesc: ticket ? (ticket.description || "").slice(0, 60) : "-",
      managerId: a.manager_id,
      managerCity: manager?.city?.name || "-",
      managerPosition: manager?.position?.name || "-",
      urgency: analysisMap[a.ticket_id]?.urgency_score || "-",
      sentiment: analysisMap[a.ticket_id]?.sentiment || "-",
    };
  });

  const businessUnitRows = businessUnits.map((office) => ({
    id: office.id_,
    city: office.city?.name || office.city_id || "-",
    address: office.address || "-",
  }));

  // Build summary rows from analyses joined with tickets
  const summaryRows = analyses
    .filter((a) => a.summary && a.summary !== "-")
    .map((a) => {
      const ticket = tickets.find((t) => String(t.id_) === String(a.ticket_id)) || {};
      const assign = assignmentMap[a.ticket_id];
      const manager = assign ? managers.find((m) => m.id_ === assign.manager_id) : null;
      return {
        ticketId: a.ticket_id,
        summary: a.summary,
        requestType: a.request_type || "-",
        sentiment: a.sentiment || "-",
        urgency: a.urgency_score || "-",
        language: a.language || "-",
        segment: ticket.segment?.name || "-",
        description: (ticket.description || "").slice(0, 120),
        assignedManager: manager ? `Manager #${manager.id_} (${manager.city?.name || "?"})` : "Unassigned",
        geo: a.formatted_address || a.geo?.formatted_address || "",
      };
    })
    .sort((a, b) => {
      const aU = a.urgency === "-" ? 0 : parseInt(a.urgency, 10) || 0;
      const bU = b.urgency === "-" ? 0 : parseInt(b.urgency, 10) || 0;
      return bU - aU;
    });

  return (
    <Box
      sx={{
        display: "flex",
        height: "100vh",
        overflow: "hidden",
        background:
          "radial-gradient(circle at 10% 10%, #e0f2fe 0%, #dbeafe 30%, #ede9fe 60%, #f8fafc 100%)",
      }}
    >
      {/* Main content */}
      <Box sx={{ flex: 1, padding: 4, display: "flex", flexDirection: "column", minHeight: 0, overflow: "hidden" }}>
        <Button
          variant="outlined"
          onClick={onBack}
          sx={{
            marginBottom: 2,
            borderRadius: 3,
            borderWidth: "2px",
            minHeight: 48,
            px: 2.5,
            fontWeight: 700,
            color: "#1d4ed8",
            borderColor: "#93c5fd",
            background: "rgba(255,255,255,0.8)",
            "&:hover": {
              borderColor: "#2563eb",
              background: "rgba(219,234,254,0.9)",
            },
          }}
        >
          Back to Upload
        </Button>

        {loading && (
          <Typography variant="h6" color="primary" gutterBottom>
            Loading data from backend...
          </Typography>
        )}

        {!!backendError && (
          <Alert severity="error" sx={{ mb: 2 }}>
            {backendError}
          </Alert>
        )}

        {!!actionError && (
          <Alert severity="error" sx={{ mb: 2 }} onClose={() => setActionError("")}>
            {actionError}
          </Alert>
        )}

        {actionStatus === "analyzing" && (
          <Alert severity="info" icon={<CircularProgress size={20} />} sx={{ mb: 2 }}>
            Running AI analysis on all tickets... This may take a minute.
          </Alert>
        )}

        {actionStatus === "routing" && (
          <Alert severity="info" icon={<CircularProgress size={20} />} sx={{ mb: 2 }}>
            Running manager routing assignment... This may take a moment.
          </Alert>
        )}

        {actionStatus === "done" && (
          <Alert severity="success" sx={{ mb: 2 }} onClose={() => setActionStatus("")}>
            Action completed successfully. Data refreshed.
          </Alert>
        )}

        <Box sx={{ flex: 1, minHeight: 0, overflowY: "auto" }}>
          {view === "load" && (
            <Card
              sx={{
                width: "100%",
                height: "100%",
                padding: 3,
                borderRadius: 4,
                boxShadow: "0 18px 40px rgba(15, 23, 42, 0.14)",
                background:
                  "linear-gradient(135deg, rgba(255,255,255,0.97) 0%, rgba(239,246,255,0.96) 52%, rgba(243,232,255,0.96) 100%)",
                display: "flex",
                flexDirection: "column",
                border: "1px solid rgba(148, 163, 184, 0.25)",
              }}
            >
              {/* Before / After toggle */}
              <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 2 }}>
                <Typography variant="subtitle2" sx={{ fontWeight: 700, color: "#475569", mr: 1 }}>
                  View:
                </Typography>
                <Button
                  size="small"
                  variant={loadMode === "before" ? "contained" : "outlined"}
                  onClick={() => setLoadMode("before")}
                  sx={{
                    borderRadius: 2,
                    textTransform: "none",
                    fontWeight: 700,
                    fontSize: "0.8rem",
                    minWidth: 100,
                    ...(loadMode === "before"
                      ? { background: "#2563eb", "&:hover": { background: "#1d4ed8" } }
                      : { color: "#2563eb", borderColor: "#93c5fd" }),
                  }}
                >
                  Before Routing
                </Button>
                <Button
                  size="small"
                  variant={loadMode === "after" ? "contained" : "outlined"}
                  onClick={() => setLoadMode("after")}
                  sx={{
                    borderRadius: 2,
                    textTransform: "none",
                    fontWeight: 700,
                    fontSize: "0.8rem",
                    minWidth: 100,
                    ...(loadMode === "after"
                      ? { background: "#7c3aed", "&:hover": { background: "#6d28d9" } }
                      : { color: "#7c3aed", borderColor: "#c4b5fd" }),
                  }}
                >
                  After Routing
                </Button>
                {loadMode === "after" && assignments.length === 0 && (
                  <Typography variant="caption" sx={{ color: "#dc2626", ml: 1 }}>
                    No assignments yet — run routing first
                  </Typography>
                )}
              </Box>

              <Box
                sx={{
                  display: "grid",
                  gridTemplateColumns: "160px 2fr 80px 1fr",
                  gap: 2,
                  borderBottom: "1px solid rgba(148, 163, 184, 0.35)",
                  paddingBottom: 1.5,
                  marginBottom: 1,
                }}
              >
                <Typography variant="subtitle2" sx={{ fontWeight: 800, color: "#1e293b" }}>
                  Manager
                </Typography>
                <Typography variant="subtitle2" sx={{ fontWeight: 800, color: "#1e293b" }}>
                  Load Status
                </Typography>
                <Typography variant="subtitle2" sx={{ fontWeight: 800, color: "#1e293b", textAlign: "right" }}>
                  Tasks
                </Typography>
              </Box>

              <Box sx={{ overflowY: "auto", flex: 1 }}>
                {managerLoadRows.map((item) => (
                  <Box
                    key={item.managerIndex}
                    sx={{
                      display: "grid",
                      gridTemplateColumns: "160px 2fr 80px 1fr",
                      gap: 2,
                      alignItems: "center",
                      mb: 1,
                    }}
                  >
                    <Typography variant="body2" sx={{ fontWeight: 600, color: "#334155" }}>
                      {`Manager ${item.managerIndex}`}
                    </Typography>

                    <LinearProgress
                      variant="determinate"
                      value={maxLoad > 0 ? (item.displayLoad / maxLoad) * 100 : 0}
                      sx={{
                        height: 10,
                        borderRadius: 5,
                        backgroundColor: "rgba(148, 163, 184, 0.18)",
                        "& .MuiLinearProgress-bar": {
                          borderRadius: 5,
                          backgroundColor: getLoadColor(item.displayLoad, maxLoad),
                          transition: "transform 0.4s ease",
                        },
                      }}
                    />

                    <Typography variant="body2" sx={{ textAlign: "right", fontWeight: 600, color: "#475569" }}>
                      {item.displayLoad}
                    </Typography>
                  </Box>
                ))}
              </Box>

              <Box sx={{ pt: 1.5, borderTop: "1px solid rgba(148,163,184,0.25)", mt: 1 }}>
                <Typography variant="caption" sx={{ color: "#94a3b8" }}>
                  Scale: 0 – {maxLoad} (dynamic) &bull; {managerLoadRows.length} managers
                  {loadMode === "after" && ` · ${assignments.length} assignments applied`}
                </Typography>
              </Box>
            </Card>
          )}

          {view === "managers" && (
            <>
              <Typography variant="h4" gutterBottom sx={{ fontWeight: 800, color: "#0f172a" }}>
                Managers
              </Typography>
              <Table
                sx={{
                  background: "rgba(255,255,255,0.9)",
                  borderRadius: 2,
                  overflow: "hidden",
                  boxShadow: "0 10px 28px rgba(15, 23, 42, 0.10)",
                  "& .MuiTableCell-head": {
                    background: "rgba(15, 23, 42, 0.05)",
                    fontWeight: 700,
                  },
                  "& .MuiTableRow-root:nth-of-type(even)": {
                    backgroundColor: "rgba(241,245,249,0.55)",
                  },
                }}
              >
              <TableHead>
                <TableRow>
                  <TableCell>ID</TableCell>
                  <TableCell>Name</TableCell>
                  <TableCell>Position</TableCell>
                  <TableCell>City</TableCell>
                  <TableCell>Skills</TableCell>
                  <TableCell>In Progress</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {managerTableRows.length > 0 ? (
                  managerTableRows.map((row) => (
                    <TableRow key={row.id}>
                      <TableCell>{row.id}</TableCell>
                      <TableCell>{row.name}</TableCell>
                      <TableCell>{row.position}</TableCell>
                      <TableCell>{row.city}</TableCell>
                      <TableCell>{row.skills}</TableCell>
                      <TableCell>{row.inProgress}</TableCell>
                    </TableRow>
                  ))
                ) : (
                  <TableRow>
                    <TableCell colSpan={6} align="center">
                      No managers found
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
              </Table>
            </>
          )}

          {view === "tickets" && (
            <>
              <Typography variant="h4" gutterBottom sx={{ fontWeight: 800, color: "#0f172a" }}>
                Tickets
              </Typography>
              <Table
                sx={{
                  background: "rgba(255,255,255,0.9)",
                  borderRadius: 2,
                  overflow: "hidden",
                  boxShadow: "0 10px 28px rgba(15, 23, 42, 0.10)",
                  "& .MuiTableCell-head": {
                    background: "rgba(15, 23, 42, 0.05)",
                    fontWeight: 700,
                  },
                  "& .MuiTableRow-root:nth-of-type(even)": {
                    backgroundColor: "rgba(241,245,249,0.55)",
                  },
                }}
              >
                <TableHead>
                <TableRow>
                  <TableCell>ID</TableCell>
                  <TableCell>Segment</TableCell>
                  <TableCell>Description</TableCell>
                  <TableCell
                    sx={{ cursor: "pointer", userSelect: "none", "&:hover": { background: "rgba(15,23,42,0.10)" } }}
                    onClick={() =>
                      setTicketSortOrder((prev) =>
                        prev === "none" ? "desc" : prev === "desc" ? "asc" : "none"
                      )
                    }
                  >
                    Urgency {ticketSortOrder === "desc" ? "▼" : ticketSortOrder === "asc" ? "▲" : "⇅"}
                  </TableCell>
                  <TableCell>Sentiment</TableCell>
                  <TableCell>Type</TableCell>
                  <TableCell>Language</TableCell>
                  <TableCell>Assigned To</TableCell>
                  <TableCell align="center">Attachments</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {ticketTableRows.length > 0 ? (
                  [...ticketTableRows]
                    .sort((a, b) => {
                      if (ticketSortOrder === "none") return 0;
                      const aVal = a.urgency === "-" ? 0 : parseInt(a.urgency, 10) || 0;
                      const bVal = b.urgency === "-" ? 0 : parseInt(b.urgency, 10) || 0;
                      return ticketSortOrder === "desc" ? bVal - aVal : aVal - bVal;
                    })
                    .map((row) => {
                    const assign = assignmentMap[row.id];
                    return (
                      <TableRow key={row.id}>
                        <TableCell>{row.id}</TableCell>
                        <TableCell>{row.segment}</TableCell>
                        <TableCell sx={{ maxWidth: 200, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                          {row.description}
                        </TableCell>
                        <TableCell>
                          <UrgencyChip value={row.urgency} />
                        </TableCell>
                        <TableCell>
                          <SentimentChip value={row.sentiment} />
                        </TableCell>
                        <TableCell>{row.requestType}</TableCell>
                        <TableCell>{row.language}</TableCell>
                        <TableCell>{assign ? `Manager #${assign.manager_id}` : "-"}</TableCell>
                        <TableCell align="center">
                          {row.attachmentCount > 0 ? (
                            <Chip
                              label={`${row.attachmentCount} file${row.attachmentCount > 1 ? "s" : ""}`}
                              size="small"
                              onClick={() => setView("attachments")}
                              sx={{
                                bgcolor: "#dbeafe",
                                color: "#1d4ed8",
                                fontWeight: 600,
                                cursor: "pointer",
                                "&:hover": { bgcolor: "#bfdbfe" },
                              }}
                            />
                          ) : (
                            <Typography variant="caption" sx={{ color: "#94a3b8" }}>—</Typography>
                          )}
                        </TableCell>
                      </TableRow>
                    );
                  })
                ) : (
                  <TableRow>
                    <TableCell colSpan={9} align="center">
                      No tickets found
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
              </Table>
            </>
          )}

          {view === "businessUnits" && (
            <>
              <Typography variant="h4" gutterBottom sx={{ fontWeight: 800, color: "#0f172a" }}>
                Business Units
              </Typography>
              <Table
                sx={{
                  background: "rgba(255,255,255,0.9)",
                  borderRadius: 2,
                  overflow: "hidden",
                  boxShadow: "0 10px 28px rgba(15, 23, 42, 0.10)",
                  "& .MuiTableCell-head": {
                    background: "rgba(15, 23, 42, 0.05)",
                    fontWeight: 700,
                  },
                  "& .MuiTableRow-root:nth-of-type(even)": {
                    backgroundColor: "rgba(241,245,249,0.55)",
                  },
                }}
              >
                <TableHead>
                <TableRow>
                  <TableCell>ID</TableCell>
                  <TableCell>Office</TableCell>
                  <TableCell>Address</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {businessUnitRows.length > 0 ? (
                  businessUnitRows.map((row) => (
                    <TableRow key={row.id}>
                      <TableCell>{row.id}</TableCell>
                      <TableCell>{row.city}</TableCell>
                      <TableCell>{row.address}</TableCell>
                    </TableRow>
                  ))
                ) : (
                  <TableRow>
                    <TableCell colSpan={3} align="center">
                      No business units found
                    </TableCell>
                  </TableRow>
                )}
                </TableBody>
              </Table>
            </>
          )}

          {view === "summaries" && (
            <>
              <Typography variant="h4" gutterBottom sx={{ fontWeight: 800, color: "#0f172a" }}>
                AI Summaries & Recommendations
              </Typography>

              {/* ── Analysis Metrics Dashboard ── */}
              {analysisMeta.length > 0 && (() => {
                // Build meta lookup by ticket_id
                const metaMap = {};
                analysisMeta.forEach((m) => { metaMap[m.ticket_id] = m; });

                // Aggregate stats
                const totalAnalyzed = analysisMeta.length;
                const avgProcessingMs = analysisMeta.reduce((s, m) => s + (m.total_processing_ms || 0), 0) / totalAnalyzed;
                const models = [...new Set(analysisMeta.map((m) => m.model))];

                // Task latency averages
                const taskNames = ["request_type", "sentiment", "urgency_score", "language", "summary", "geo", "image_describe"];
                const taskLabels = { request_type: "Request Type", sentiment: "Sentiment", urgency_score: "Urgency", language: "Language", summary: "Summary", geo: "Geo", image_describe: "Image Describe" };
                const avgLatencies = {};
                const avgRetries = {};
                taskNames.forEach((t) => {
                  const lats = analysisMeta.map((m) => m.task_latencies?.[t] ?? 0);
                  avgLatencies[t] = lats.reduce((a, b) => a + b, 0) / totalAnalyzed;
                  const rets = analysisMeta.map((m) => m.retries_used?.[t] ?? 0);
                  avgRetries[t] = rets.reduce((a, b) => a + b, 0) / totalAnalyzed;
                });

                // Fallback frequency
                const fallbackCounts = {};
                analysisMeta.forEach((m) => {
                  (m.fallbacks_used || []).forEach((f) => {
                    fallbackCounts[f] = (fallbackCounts[f] || 0) + 1;
                  });
                });
                const totalFallbacks = Object.values(fallbackCounts).reduce((a, b) => a + b, 0);

                // Max latency task per ticket
                const maxLatencyTask = taskNames.reduce((max, t) => avgLatencies[t] > avgLatencies[max] ? t : max, taskNames[0]);

                return (
                  <Card sx={{
                    mb: 3, borderRadius: 3,
                    background: "linear-gradient(135deg, #0f172a 0%, #1e293b 100%)",
                    color: "#fff",
                    boxShadow: "0 8px 32px rgba(15, 23, 42, 0.25)",
                  }}>
                    <CardContent sx={{ p: 3 }}>
                      <Typography variant="h6" sx={{ fontWeight: 700, mb: 2, color: "#e2e8f0" }}>
                        📊 Analysis Performance Metrics
                      </Typography>

                      {/* KPIs row */}
                      <Box sx={{ display: "flex", gap: 2, mb: 3, flexWrap: "wrap" }}>
                        {[
                          { label: "Tickets Analyzed", value: totalAnalyzed, color: "#38bdf8" },
                          { label: "Avg Processing", value: `${avgProcessingMs.toFixed(0)}ms`, color: "#a78bfa" },
                          { label: "Model", value: models.join(", "), color: "#34d399" },
                          { label: "Total Fallbacks", value: totalFallbacks, color: totalFallbacks > 0 ? "#f87171" : "#34d399" },
                        ].map((kpi) => (
                          <Box key={kpi.label} sx={{
                            flex: "1 1 140px", minWidth: 140,
                            bgcolor: "rgba(255,255,255,0.06)", borderRadius: 2, p: 2,
                            border: "1px solid rgba(255,255,255,0.1)",
                          }}>
                            <Typography variant="caption" sx={{ color: "#94a3b8", fontWeight: 600, textTransform: "uppercase", fontSize: "0.65rem", letterSpacing: 1 }}>
                              {kpi.label}
                            </Typography>
                            <Typography variant="h5" sx={{ fontWeight: 800, color: kpi.color, mt: 0.5 }}>
                              {kpi.value}
                            </Typography>
                          </Box>
                        ))}
                      </Box>

                      {/* Task Latencies bar chart */}
                      <Typography variant="subtitle2" sx={{ color: "#cbd5e1", fontWeight: 700, mb: 1.5 }}>
                        Average Task Latencies (ms)
                      </Typography>
                      <Box sx={{ display: "flex", flexDirection: "column", gap: 1, mb: 3 }}>
                        {taskNames.map((t) => {
                          const val = avgLatencies[t];
                          const maxVal = Math.max(...Object.values(avgLatencies), 1);
                          const pct = (val / maxVal) * 100;
                          const barColor = t === maxLatencyTask ? "#f59e0b" : "#38bdf8";
                          return (
                            <Box key={t} sx={{ display: "flex", alignItems: "center", gap: 1 }}>
                              <Typography variant="caption" sx={{ color: "#94a3b8", width: 100, textAlign: "right", fontSize: "0.7rem", fontWeight: 600 }}>
                                {taskLabels[t]}
                              </Typography>
                              <Box sx={{ flex: 1, height: 18, bgcolor: "rgba(255,255,255,0.06)", borderRadius: 1, overflow: "hidden", position: "relative" }}>
                                <Box sx={{ width: `${Math.max(pct, 2)}%`, height: "100%", bgcolor: barColor, borderRadius: 1, transition: "width 0.5s ease" }} />
                              </Box>
                              <Typography variant="caption" sx={{ color: "#e2e8f0", width: 60, fontWeight: 700, fontSize: "0.72rem" }}>
                                {val.toFixed(1)}ms
                              </Typography>
                            </Box>
                          );
                        })}
                      </Box>

                      {/* Retries & Fallbacks row */}
                      <Box sx={{ display: "flex", gap: 3, flexWrap: "wrap" }}>
                        {/* Avg retries */}
                        <Box sx={{ flex: "1 1 280px" }}>
                          <Typography variant="subtitle2" sx={{ color: "#cbd5e1", fontWeight: 700, mb: 1 }}>
                            Average Retries per Task
                          </Typography>
                          <Box sx={{ display: "flex", flexWrap: "wrap", gap: 1 }}>
                            {taskNames.map((t) => (
                              <Chip
                                key={t}
                                label={`${taskLabels[t]}: ${avgRetries[t].toFixed(2)}`}
                                size="small"
                                sx={{
                                  bgcolor: avgRetries[t] > 0.5 ? "rgba(248,113,113,0.2)" : "rgba(52,211,153,0.15)",
                                  color: avgRetries[t] > 0.5 ? "#fca5a5" : "#6ee7b7",
                                  fontWeight: 600, fontSize: "0.7rem",
                                  border: `1px solid ${avgRetries[t] > 0.5 ? "rgba(248,113,113,0.3)" : "rgba(52,211,153,0.25)"}`,
                                }}
                              />
                            ))}
                          </Box>
                        </Box>

                        {/* Fallback breakdown */}
                        {totalFallbacks > 0 && (
                          <Box sx={{ flex: "1 1 200px" }}>
                            <Typography variant="subtitle2" sx={{ color: "#cbd5e1", fontWeight: 700, mb: 1 }}>
                              Fallbacks Used
                            </Typography>
                            <Box sx={{ display: "flex", flexWrap: "wrap", gap: 1 }}>
                              {Object.entries(fallbackCounts).map(([name, count]) => (
                                <Chip
                                  key={name}
                                  label={`${name}: ${count}`}
                                  size="small"
                                  sx={{
                                    bgcolor: "rgba(248,113,113,0.2)", color: "#fca5a5",
                                    fontWeight: 700, fontSize: "0.7rem",
                                    border: "1px solid rgba(248,113,113,0.3)",
                                  }}
                                />
                              ))}
                            </Box>
                          </Box>
                        )}
                      </Box>

                      {/* Per-ticket detail table */}
                      <Box sx={{ mt: 3 }}>
                        <Typography variant="subtitle2" sx={{ color: "#cbd5e1", fontWeight: 700, mb: 1 }}>
                          Per-Ticket Breakdown
                        </Typography>
                        <Box sx={{ maxHeight: 280, overflow: "auto", borderRadius: 2, border: "1px solid rgba(255,255,255,0.08)" }}>
                          <Table size="small" sx={{ "& td, & th": { color: "#e2e8f0", borderColor: "rgba(255,255,255,0.06)", fontSize: "0.72rem", py: 0.8 } }}>
                            <TableHead>
                              <TableRow sx={{ bgcolor: "rgba(255,255,255,0.04)" }}>
                                <TableCell sx={{ fontWeight: 700 }}>Ticket</TableCell>
                                <TableCell align="right" sx={{ fontWeight: 700 }}>Total (ms)</TableCell>
                                <TableCell align="right" sx={{ fontWeight: 700 }}>Slowest Task</TableCell>
                                <TableCell align="right" sx={{ fontWeight: 700 }}>Retries</TableCell>
                                <TableCell sx={{ fontWeight: 700 }}>Fallbacks</TableCell>
                              </TableRow>
                            </TableHead>
                            <TableBody>
                              {analysisMeta.map((m) => {
                                const lat = m.task_latencies || {};
                                const ret = m.retries_used || {};
                                // find slowest task
                                let slowest = "-";
                                let slowestVal = 0;
                                taskNames.forEach((t) => {
                                  if ((lat[t] || 0) > slowestVal) { slowestVal = lat[t]; slowest = taskLabels[t]; }
                                });
                                const totalRetries = taskNames.reduce((s, t) => s + (ret[t] || 0), 0);
                                return (
                                  <TableRow key={m.ticket_id} sx={{ "&:hover": { bgcolor: "rgba(255,255,255,0.04)" } }}>
                                    <TableCell>
                                      <Chip label={`#${String(m.ticket_id).slice(0, 8)}…`} size="small"
                                        sx={{ bgcolor: "rgba(56,189,248,0.15)", color: "#7dd3fc", fontWeight: 700, fontSize: "0.68rem" }} />
                                    </TableCell>
                                    <TableCell align="right" sx={{ fontWeight: 700, color: (m.total_processing_ms || 0) > 10000 ? "#f87171" : "#34d399" }}>
                                      {(m.total_processing_ms || 0).toFixed(0)}
                                    </TableCell>
                                    <TableCell align="right">
                                      {slowest} ({slowestVal.toFixed(0)}ms)
                                    </TableCell>
                                    <TableCell align="right" sx={{ color: totalRetries > 0 ? "#fbbf24" : "#6ee7b7" }}>
                                      {totalRetries}
                                    </TableCell>
                                    <TableCell>
                                      {(m.fallbacks_used || []).length === 0
                                        ? <Chip label="None" size="small" sx={{ bgcolor: "rgba(52,211,153,0.15)", color: "#6ee7b7", fontSize: "0.65rem" }} />
                                        : (m.fallbacks_used || []).map((f) => (
                                          <Chip key={f} label={f} size="small"
                                            sx={{ bgcolor: "rgba(248,113,113,0.15)", color: "#fca5a5", fontSize: "0.65rem", mr: 0.5 }} />
                                        ))
                                      }
                                    </TableCell>
                                  </TableRow>
                                );
                              })}
                            </TableBody>
                          </Table>
                        </Box>
                      </Box>
                    </CardContent>
                  </Card>
                );
              })()}

              {summaryRows.length === 0 ? (
                <Alert severity="info" sx={{ mb: 2 }}>
                  No AI summaries available yet. Click "Run AI Analysis" to generate them.
                </Alert>
              ) : (
                <Box sx={{ display: "flex", flexDirection: "column", gap: 2.5 }}>
                  {summaryRows.map((row) => (
                    <Card
                      key={row.ticketId}
                      sx={{
                        borderRadius: 3,
                        boxShadow: "0 6px 20px rgba(15, 23, 42, 0.10)",
                        background: "linear-gradient(135deg, rgba(255,255,255,0.98) 0%, rgba(241,245,249,0.95) 100%)",
                        border: "1px solid rgba(148, 163, 184, 0.22)",
                        transition: "box-shadow 200ms ease, transform 200ms ease",
                        "&:hover": {
                          boxShadow: "0 12px 32px rgba(15, 23, 42, 0.16)",
                          transform: "translateY(-2px)",
                        },
                      }}
                    >
                      <CardContent sx={{ p: 2.5 }}>
                        {/* Header row */}
                        <Box sx={{ display: "flex", alignItems: "center", gap: 1.5, mb: 1.5, flexWrap: "wrap" }}>
                          <Chip
                            label={`Ticket #${row.ticketId}`}
                            size="small"
                            sx={{ bgcolor: "#1e293b", color: "#fff", fontWeight: 700, "& .MuiChip-label": { color: "#fff" } }}
                          />
                          <UrgencyChip value={row.urgency} />
                          <SentimentChip value={row.sentiment} />
                          <Chip
                            label={row.requestType}
                            size="small"
                            variant="outlined"
                            sx={{ fontWeight: 600, borderColor: "#93c5fd", color: "#1d4ed8" }}
                          />
                          <Chip
                            label={row.language}
                            size="small"
                            variant="outlined"
                            sx={{ fontWeight: 600, borderColor: "#c4b5fd", color: "#7c3aed" }}
                          />
                          {row.segment !== "-" && (
                            <Chip
                              label={row.segment}
                              size="small"
                              variant="outlined"
                              sx={{ fontWeight: 600, borderColor: "#6ee7b7", color: "#059669" }}
                            />
                          )}
                        </Box>

                        {/* Original description (collapsed) */}
                        {row.description && (
                          <Typography
                            variant="body2"
                            sx={{
                              color: "#64748b",
                              fontStyle: "italic",
                              mb: 1.5,
                              fontSize: "0.82rem",
                              lineHeight: 1.5,
                              maxHeight: 44,
                              overflow: "hidden",
                              textOverflow: "ellipsis",
                            }}
                          >
                            "{row.description}..."
                          </Typography>
                        )}

                        <Divider sx={{ mb: 1.5, borderColor: "rgba(148,163,184,0.25)" }} />

                        {/* AI Summary */}
                        <Typography
                          variant="body1"
                          sx={{
                            color: "#0f172a",
                            fontWeight: 500,
                            lineHeight: 1.7,
                            fontSize: "0.95rem",
                            whiteSpace: "pre-wrap",
                          }}
                        >
                          {row.summary}
                        </Typography>

                        {/* Footer */}
                        <Box sx={{ display: "flex", alignItems: "center", gap: 2, mt: 1.5, flexWrap: "wrap" }}>
                          <Typography variant="caption" sx={{ color: "#64748b", fontWeight: 600 }}>
                            {row.assignedManager}
                          </Typography>
                          {row.geo && (
                            <Typography variant="caption" sx={{ color: "#94a3b8" }}>
                              {row.geo}
                            </Typography>
                          )}
                        </Box>
                      </CardContent>
                    </Card>
                  ))}
                </Box>
              )}
            </>
          )}

          {view === "attachments" && (
            <>
              <Box sx={{ display: "flex", alignItems: "center", gap: 2, mb: 2, flexWrap: "wrap" }}>
                <Typography variant="h4" sx={{ fontWeight: 800, color: "#0f172a" }}>
                  Ticket Attachments
                </Typography>
                <Button
                  variant="contained"
                  size="small"
                  startIcon={<CloudUploadIcon />}
                  disabled={uploadingImage}
                  onClick={() => {
                    setUploadTargetTicketId(null);
                    fileInputRef.current?.click();
                  }}
                  sx={{
                    borderRadius: 2,
                    fontWeight: 700,
                    textTransform: "none",
                    background: "linear-gradient(120deg, #0ea5e9 0%, #2563eb 100%)",
                    "&:hover": { background: "linear-gradient(120deg, #0284c7 0%, #1d4ed8 100%)" },
                  }}
                >
                  {uploadingImage ? "Uploading..." : "Auto-Sync Upload"}
                </Button>
                <Typography variant="caption" sx={{ color: "#64748b", maxWidth: 360 }}>
                  Drop images whose filenames match CSV Вложения column and they'll be linked automatically.
                </Typography>
                <input
                  ref={fileInputRef}
                  type="file"
                  accept="image/*"
                  multiple
                  style={{ display: "none" }}
                  onChange={handleImageUpload}
                />
                <input
                  ref={manualSyncInputRef}
                  type="file"
                  accept="image/*"
                  style={{ display: "none" }}
                  onChange={handleManualSync}
                />
              </Box>

              {!!uploadError && (
                <Alert severity="error" sx={{ mb: 2 }} onClose={() => setUploadError("")}>
                  {uploadError}
                </Alert>
              )}

              {(() => {
                // Build joint table rows: one row per attachment, with ticket ID where linked
                const rows = [];

                // From ticketsWithAttachments — these have ticket links
                const seenAttKeys = new Set();
                ticketsWithAttachments.forEach((t) => {
                  const tid = t.id_ || t.id;
                  (t.attachments || []).forEach((att) => {
                    const key = att.key || "";
                    const fname = key.split("/").pop() || key;
                    const isImage = (att.type?.name || key).match(/image|\.png|\.jpg|\.jpeg|\.gif|\.webp/i);
                    const hasUrl = !!att.url;
                    seenAttKeys.add(key);
                    rows.push({
                      ticketId: tid,
                      attId: att.id_ || att.id,
                      filename: fname,
                      s3Key: key,
                      type: att.type?.name || "-",
                      url: att.url || null,
                      isImage: !!isImage,
                      uploaded: hasUrl,
                    });
                  });
                });

                // From attachmentsList — standalone / unlinked
                attachmentsList.forEach((att) => {
                  const key = att.key || "";
                  if (seenAttKeys.has(key)) return;
                  const fname = key.split("/").pop() || key;
                  const isImage = (att.type?.name || key).match(/image|\.png|\.jpg|\.jpeg|\.gif|\.webp/i);
                  // Try to infer ticket from key pattern tickets/<id>/...
                  const keyMatch = key.match(/^tickets\/(\d+)\//);
                  const inferredTid = keyMatch ? parseInt(keyMatch[1], 10) : null;
                  rows.push({
                    ticketId: inferredTid,
                    attId: att.id_ || att.id,
                    filename: fname,
                    s3Key: key,
                    type: att.type?.name || "-",
                    url: att.url || null,
                    isImage: !!isImage,
                    uploaded: !!att.url,
                  });
                });

                // Sort: by ticket ID (nulls last), then filename
                rows.sort((a, b) => {
                  if (a.ticketId && !b.ticketId) return -1;
                  if (!a.ticketId && b.ticketId) return 1;
                  if (a.ticketId && b.ticketId && a.ticketId !== b.ticketId) return a.ticketId - b.ticketId;
                  return (a.filename || "").localeCompare(b.filename || "");
                });

                if (rows.length === 0) {
                  return (
                    <Alert severity="info">
                      No attachments found. Upload images using the button above, or re-sync tickets CSV to register attachments from the Вложения column.
                    </Alert>
                  );
                }

                return (
                  <Table
                    sx={{
                      background: "rgba(255,255,255,0.9)",
                      borderRadius: 2,
                      overflow: "hidden",
                      boxShadow: "0 10px 28px rgba(15, 23, 42, 0.10)",
                      "& .MuiTableCell-head": {
                        background: "rgba(15, 23, 42, 0.05)",
                        fontWeight: 700,
                      },
                      "& .MuiTableRow-root:nth-of-type(even)": {
                        backgroundColor: "rgba(241,245,249,0.55)",
                      },
                    }}
                  >
                    <TableHead>
                      <TableRow>
                        <TableCell>Ticket ID</TableCell>
                        <TableCell>Filename</TableCell>
                        <TableCell>Type</TableCell>
                        <TableCell>Preview</TableCell>
                        <TableCell>URL / S3 Key</TableCell>
                        <TableCell>Status</TableCell>
                        <TableCell align="center">Actions</TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {rows.map((row, idx) => (
                        <TableRow key={row.attId || idx}>
                          <TableCell>
                            {row.ticketId ? (
                              <Chip
                                label={`#${row.ticketId}`}
                                size="small"
                                sx={{ bgcolor: "#1e293b", color: "#fff", fontWeight: 700, "& .MuiChip-label": { color: "#fff" } }}
                              />
                            ) : (
                              <Typography variant="caption" sx={{ color: "#94a3b8", fontStyle: "italic" }}>Unlinked</Typography>
                            )}
                          </TableCell>
                          <TableCell sx={{ fontWeight: 600, color: "#334155", maxWidth: 200, wordBreak: "break-all" }}>
                            {row.filename}
                          </TableCell>
                          <TableCell>
                            <Typography variant="caption" sx={{ color: "#64748b" }}>{row.type}</Typography>
                          </TableCell>
                          <TableCell>
                            {row.isImage && row.url ? (
                              <Box
                                component="img"
                                src={row.url}
                                alt={row.filename}
                                onClick={() => setLightboxUrl(row.url)}
                                onError={(e) => { e.target.style.display = "none"; }}
                                sx={{
                                  width: 48,
                                  height: 48,
                                  objectFit: "cover",
                                  borderRadius: 1,
                                  cursor: "pointer",
                                  border: "1px solid rgba(148,163,184,0.3)",
                                  transition: "transform 150ms ease",
                                  "&:hover": { transform: "scale(1.15)" },
                                }}
                              />
                            ) : (
                              <Typography variant="caption" sx={{ color: "#94a3b8" }}>—</Typography>
                            )}
                          </TableCell>
                          <TableCell sx={{ maxWidth: 280 }}>
                            {row.url ? (
                              <Typography
                                variant="caption"
                                component="a"
                                href={row.url}
                                target="_blank"
                                rel="noopener noreferrer"
                                sx={{ color: "#2563eb", textDecoration: "underline", wordBreak: "break-all", cursor: "pointer" }}
                              >
                                {row.s3Key}
                              </Typography>
                            ) : (
                              <Typography variant="caption" sx={{ color: "#94a3b8", wordBreak: "break-all" }}>
                                {row.s3Key}
                              </Typography>
                            )}
                          </TableCell>
                          <TableCell>
                            {row.uploaded ? (
                              <Chip
                                icon={<CheckCircleIcon sx={{ fontSize: 16 }} />}
                                label="Uploaded"
                                size="small"
                                sx={{ bgcolor: "#dcfce7", color: "#16a34a", fontWeight: 600, "& .MuiChip-icon": { color: "#16a34a" } }}
                              />
                            ) : (
                              <Chip
                                icon={<HourglassEmptyIcon sx={{ fontSize: 16 }} />}
                                label="Pending"
                                size="small"
                                sx={{ bgcolor: "#fef3c7", color: "#d97706", fontWeight: 600, "& .MuiChip-icon": { color: "#d97706" } }}
                              />
                            )}
                          </TableCell>
                          <TableCell align="center">
                            {!row.uploaded && (
                              <Button
                                size="small"
                                variant="outlined"
                                startIcon={<CloudUploadIcon sx={{ fontSize: 14 }} />}
                                disabled={uploadingImage}
                                onClick={() => {
                                  setManualSyncTarget({ s3Key: row.s3Key, attId: row.attId });
                                  setTimeout(() => manualSyncInputRef.current?.click(), 50);
                                }}
                                sx={{ borderRadius: 2, textTransform: "none", fontWeight: 600, fontSize: "0.72rem" }}
                              >
                                Upload to {row.s3Key.split("/").pop()}
                              </Button>
                            )}
                            {row.uploaded && row.isImage && row.url && (
                              <IconButton
                                size="small"
                                onClick={() => setLightboxUrl(row.url)}
                                sx={{ color: "#2563eb" }}
                              >
                                <LinkIcon fontSize="small" />
                              </IconButton>
                            )}
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                );
              })()}

              {/* Image lightbox dialog */}
              <Dialog open={!!lightboxUrl} onClose={() => setLightboxUrl(null)} maxWidth="lg">
                <DialogContent sx={{ p: 0, position: "relative", bgcolor: "#000" }}>
                  <IconButton
                    onClick={() => setLightboxUrl(null)}
                    sx={{ position: "absolute", top: 8, right: 8, color: "#fff", bgcolor: "rgba(0,0,0,0.5)", "&:hover": { bgcolor: "rgba(0,0,0,0.7)" } }}
                  >
                    <CloseIcon />
                  </IconButton>
                  {lightboxUrl && (
                    <img src={lightboxUrl} alt="Attachment" style={{ maxWidth: "90vw", maxHeight: "85vh", display: "block" }} />
                  )}
                </DialogContent>
              </Dialog>
            </>
          )}

          {view === "assignments" && (
            <>
              <Typography variant="h4" gutterBottom sx={{ fontWeight: 800, color: "#0f172a" }}>
                Routing Assignments
              </Typography>
              {assignmentRows.length === 0 ? (
                <Alert severity="info" sx={{ mb: 2 }}>
                  No assignments yet. Click "Run Routing" in the sidebar to assign managers to tickets.
                </Alert>
              ) : (
                <Table
                  sx={{
                    background: "rgba(255,255,255,0.9)",
                    borderRadius: 2,
                    overflow: "hidden",
                    boxShadow: "0 10px 28px rgba(15, 23, 42, 0.10)",
                    "& .MuiTableCell-head": {
                      background: "rgba(15, 23, 42, 0.05)",
                      fontWeight: 700,
                    },
                    "& .MuiTableRow-root:nth-of-type(even)": {
                      backgroundColor: "rgba(241,245,249,0.55)",
                    },
                  }}
                >
                  <TableHead>
                    <TableRow>
                      <TableCell>Ticket ID</TableCell>
                      <TableCell>Ticket Description</TableCell>
                      <TableCell>Manager ID</TableCell>
                      <TableCell>Manager Position</TableCell>
                      <TableCell>Manager City</TableCell>
                      <TableCell>Urgency</TableCell>
                      <TableCell>Sentiment</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {assignmentRows.map((row) => (
                      <TableRow key={row.ticketId}>
                        <TableCell>{row.ticketId}</TableCell>
                        <TableCell sx={{ maxWidth: 200, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                          {row.ticketDesc}
                        </TableCell>
                        <TableCell>{row.managerId}</TableCell>
                        <TableCell>{row.managerPosition}</TableCell>
                        <TableCell>{row.managerCity}</TableCell>
                        <TableCell><UrgencyChip value={row.urgency} /></TableCell>
                        <TableCell><SentimentChip value={row.sentiment} /></TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </>
          )}
        </Box>
      </Box>

      {/* Sidebar */}
      <Box
        sx={{
          width: 300,
          minWidth: 300,
          padding: 2,
          borderLeft: "1px solid rgba(148, 163, 184, 0.35)",
          display: "flex",
          flexDirection: "column",
          justifyContent: "space-between",
          overflowY: "auto",
          background:
            "linear-gradient(180deg, rgba(224,242,254,0.75) 0%, rgba(219,234,254,0.66) 52%, rgba(237,233,254,0.66) 100%)",
          boxShadow: "-12px 0 24px rgba(15, 23, 42, 0.06)",
          backdropFilter: "blur(6px)",
        }}
      >
        <Box>
          <Button
            fullWidth
            sx={sidebarButtonSx(view === "load")}
            variant={view === "load" ? "contained" : "outlined"}
            onClick={() => setView("load")}
          >
            Current Load
          </Button>

          <Button
            fullWidth
            sx={sidebarButtonSx(view === "managers")}
            variant={view === "managers" ? "contained" : "outlined"}
            onClick={() => setView("managers")}
          >
            Managers
          </Button>

          <Button
            fullWidth
            sx={sidebarButtonSx(view === "tickets")}
            variant={view === "tickets" ? "contained" : "outlined"}
            onClick={() => setView("tickets")}
          >
            Tickets
          </Button>

          <Button
            fullWidth
            sx={sidebarButtonSx(view === "summaries")}
            variant={view === "summaries" ? "contained" : "outlined"}
            onClick={() => setView("summaries")}
          >
            AI Summaries
          </Button>

          <Button
            fullWidth
            sx={sidebarButtonSx(view === "attachments")}
            variant={view === "attachments" ? "contained" : "outlined"}
            onClick={() => setView("attachments")}
          >
            Attachments
          </Button>

          <Button
            fullWidth
            sx={sidebarButtonSx(view === "businessUnits")}
            variant={view === "businessUnits" ? "contained" : "outlined"}
            onClick={() => setView("businessUnits")}
          >
            Business Units
          </Button>

          <Button
            fullWidth
            sx={sidebarButtonSx(view === "assignments")}
            variant={view === "assignments" ? "contained" : "outlined"}
            onClick={() => setView("assignments")}
          >
            Assignments
          </Button>
        </Box>

        <Box sx={{ display: "flex", flexDirection: "column", gap: 1 }}>
          <Button
            variant="contained"
            disabled={actionStatus === "analyzing" || actionStatus === "routing"}
            onClick={handleRunAnalysis}
            sx={{
              borderRadius: 3,
              minHeight: 44,
              fontWeight: 700,
              fontSize: "0.85rem",
              background: "linear-gradient(120deg, #0ea5e9 0%, #2563eb 100%)",
              boxShadow: "0 8px 20px rgba(37, 99, 235, 0.30)",
              "&:hover": {
                background: "linear-gradient(120deg, #0284c7 0%, #1d4ed8 100%)",
              },
            }}
          >
            {actionStatus === "analyzing" ? "Analyzing..." : "Run AI Analysis"}
          </Button>

          <Button
            variant="contained"
            disabled={actionStatus === "analyzing" || actionStatus === "routing"}
            onClick={handleRunRouting}
            sx={{
              borderRadius: 3,
              minHeight: 44,
              fontWeight: 700,
              fontSize: "0.85rem",
              background: "linear-gradient(120deg, #7c3aed 0%, #6d28d9 100%)",
              boxShadow: "0 8px 20px rgba(109, 40, 217, 0.30)",
              "&:hover": {
                background: "linear-gradient(120deg, #6d28d9 0%, #5b21b6 100%)",
              },
            }}
          >
            {actionStatus === "routing" ? "Routing..." : "Run Routing"}
          </Button>

          <Button
            variant="contained"
            onClick={handleRefresh}
            disabled={loading}
            sx={{
              borderRadius: 3,
              minHeight: 44,
              fontWeight: 700,
              fontSize: "0.85rem",
              background: "linear-gradient(120deg, #ec4899 0%, #db2777 45%, #7e22ce 100%)",
              boxShadow: "0 8px 20px rgba(190, 24, 93, 0.30)",
              "&:hover": {
                background: "linear-gradient(120deg, #db2777 0%, #be185d 45%, #6b21a8 100%)",
              },
            }}
          >
            Refresh Data
          </Button>

          <Button
            variant="contained"
            onClick={() => window.open("http://localhost:3000", "_blank")}
            sx={{
              borderRadius: 3,
              minHeight: 48,
              fontWeight: 700,
              fontSize: "0.85rem",
              background: "linear-gradient(120deg, #10b981 0%, #059669 50%, #047857 100%)",
              boxShadow: "0 8px 20px rgba(5, 150, 105, 0.30)",
              display: "flex",
              alignItems: "center",
              gap: 1,
              "&:hover": {
                background: "linear-gradient(120deg, #059669 0%, #047857 50%, #065f46 100%)",
              },
            }}
          >
            <span role="img" aria-label="AI" style={{ fontSize: "1.2rem" }}>🤖</span>
            AI SQL Assistant
          </Button>
        </Box>
      </Box>
    </Box>
  );
};

export default DashboardPage;
