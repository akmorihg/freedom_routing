import React, { useState, useEffect, useCallback, useRef } from "react";
import {
  Alert,
  Box,
  Typography,
  Button,
  Card,
  CardContent,
  CardMedia,
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
import {
  listManagers,
  listOffices,
  listTickets,
  listTicketAssignments,
  listTicketAnalyses,
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
  const [uploadTargetTicketId, setUploadTargetTicketId] = useState(null);

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
    try {
      [attachResult, ticketsAttResult] = await Promise.all([
        listAttachments(),
        listTicketsWithAttachments(),
      ]);
    } catch (_e) { /* ignore if attachment endpoints fail */ }

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

  // ── Image upload handler ───────────────────────────────────────────
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

      for (const file of files) {
        const mime = file.type || "application/octet-stream";
        const typeId = await ensureType(mime);

        // Choose S3 key based on target ticket
        const prefix = uploadTargetTicketId ? `tickets/${uploadTargetTicketId}` : "uploads";
        const s3Key = `${prefix}/${file.name}`;

        // Upload to MinIO via backend
        await uploadFileToS3(file, s3Key, "static");

        // Create DB attachment record
        const att = await createAttachment({ type_id: typeId, key: s3Key });

        // Link to ticket if a target was specified
        if (uploadTargetTicketId && att.id_) {
          try {
            await addAttachmentsToTicket(uploadTargetTicketId, [att.id_]);
          } catch (_) { /* non-fatal */ }
        }
      }

      await fetchData();
    } catch (err) {
      setUploadError(`Image upload failed: ${err.message}`);
    } finally {
      setUploadingImage(false);
      setUploadTargetTicketId(null);
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
                      </TableRow>
                    );
                  })
                ) : (
                  <TableRow>
                    <TableCell colSpan={8} align="center">
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
                  {uploadingImage ? "Uploading..." : "Upload Image"}
                </Button>
                <input
                  ref={fileInputRef}
                  type="file"
                  accept="image/*"
                  multiple
                  style={{ display: "none" }}
                  onChange={handleImageUpload}
                />
              </Box>

              {!!uploadError && (
                <Alert severity="error" sx={{ mb: 2 }} onClose={() => setUploadError("")}>
                  {uploadError}
                </Alert>
              )}

              {(() => {
                // Build a map of ticket_id → ticket info + its attachments
                const ticketAttachmentMap = {};
                ticketsWithAttachments.forEach((t) => {
                  const tid = t.id_ || t.id;
                  if (t.attachments && t.attachments.length > 0) {
                    ticketAttachmentMap[tid] = {
                      ticketId: tid,
                      description: (t.description || "").slice(0, 100),
                      segment: t.segment?.name || "-",
                      attachments: t.attachments,
                    };
                  }
                });

                // Also include standalone attachments not linked to tickets
                const linkedKeys = new Set();
                Object.values(ticketAttachmentMap).forEach((t) =>
                  t.attachments.forEach((a) => linkedKeys.add(a.key))
                );
                const standaloneAttachments = attachmentsList.filter(
                  (a) => !linkedKeys.has(a.key)
                );

                const ticketEntries = Object.values(ticketAttachmentMap);
                const hasAny = ticketEntries.length > 0 || standaloneAttachments.length > 0;

                if (!hasAny) {
                  return (
                    <Alert severity="info">
                      No attachments found. Upload images using the button above, or re-sync tickets CSV to register attachments from the Вложения column.
                    </Alert>
                  );
                }

                return (
                  <Box sx={{ display: "flex", flexDirection: "column", gap: 3 }}>
                    {ticketEntries.map((entry) => (
                      <Card
                        key={entry.ticketId}
                        sx={{
                          borderRadius: 3,
                          boxShadow: "0 6px 20px rgba(15, 23, 42, 0.10)",
                          background: "linear-gradient(135deg, rgba(255,255,255,0.98) 0%, rgba(241,245,249,0.95) 100%)",
                          border: "1px solid rgba(148, 163, 184, 0.22)",
                        }}
                      >
                        <CardContent sx={{ p: 2.5 }}>
                          <Box sx={{ display: "flex", alignItems: "center", gap: 1.5, mb: 1.5, flexWrap: "wrap" }}>
                            <Chip
                              label={`Ticket #${entry.ticketId}`}
                              size="small"
                              sx={{ bgcolor: "#1e293b", color: "#fff", fontWeight: 700, "& .MuiChip-label": { color: "#fff" } }}
                            />
                            <Chip label={entry.segment} size="small" variant="outlined" sx={{ fontWeight: 600, borderColor: "#6ee7b7", color: "#059669" }} />
                            <Typography variant="body2" sx={{ color: "#64748b", fontStyle: "italic" }}>
                              {entry.description}...
                            </Typography>
                            <Button
                              size="small"
                              variant="outlined"
                              disabled={uploadingImage}
                              onClick={() => {
                                setUploadTargetTicketId(entry.ticketId);
                                fileInputRef.current?.click();
                              }}
                              sx={{ ml: "auto", borderRadius: 2, textTransform: "none", fontWeight: 600, fontSize: "0.75rem" }}
                            >
                              + Add Image
                            </Button>
                          </Box>
                          <Box sx={{ display: "flex", gap: 2, flexWrap: "wrap" }}>
                            {entry.attachments.map((att) => {
                              const isImage = (att.type?.name || att.key || "").match(/image|\.png|\.jpg|\.jpeg|\.gif|\.webp/i);
                              const url = att.url;
                              return (
                                <Box
                                  key={att.id_ || att.key}
                                  sx={{
                                    width: 160,
                                    borderRadius: 2,
                                    overflow: "hidden",
                                    border: "1px solid rgba(148,163,184,0.3)",
                                    background: "#f8fafc",
                                    cursor: isImage && url ? "pointer" : "default",
                                    transition: "box-shadow 200ms ease, transform 200ms ease",
                                    "&:hover": { boxShadow: "0 8px 24px rgba(15,23,42,0.14)", transform: "translateY(-2px)" },
                                  }}
                                  onClick={() => isImage && url && setLightboxUrl(url)}
                                >
                                  {isImage && url ? (
                                    <CardMedia
                                      component="img"
                                      image={url}
                                      alt={att.key}
                                      sx={{ height: 120, objectFit: "cover" }}
                                      onError={(e) => { e.target.style.display = "none"; }}
                                    />
                                  ) : (
                                    <Box sx={{ height: 120, display: "flex", alignItems: "center", justifyContent: "center", bgcolor: "#e2e8f0" }}>
                                      <Typography variant="caption" sx={{ color: "#64748b", textAlign: "center", px: 1 }}>
                                        {att.type?.name || "File"}
                                      </Typography>
                                    </Box>
                                  )}
                                  <Box sx={{ p: 1 }}>
                                    <Typography variant="caption" sx={{ color: "#475569", fontSize: "0.7rem", wordBreak: "break-all", display: "block", lineHeight: 1.3 }}>
                                      {(att.key || "").split("/").pop()}
                                    </Typography>
                                    {att.type?.name && (
                                      <Typography variant="caption" sx={{ color: "#94a3b8", fontSize: "0.65rem" }}>
                                        {att.type.name}
                                      </Typography>
                                    )}
                                  </Box>
                                </Box>
                              );
                            })}
                          </Box>
                        </CardContent>
                      </Card>
                    ))}

                    {standaloneAttachments.length > 0 && (
                      <Card sx={{ borderRadius: 3, boxShadow: "0 6px 20px rgba(15,23,42,0.10)", background: "rgba(255,255,255,0.97)", border: "1px solid rgba(148,163,184,0.22)" }}>
                        <CardContent sx={{ p: 2.5 }}>
                          <Typography variant="h6" sx={{ fontWeight: 700, color: "#334155", mb: 1.5 }}>
                            Unlinked Attachments
                          </Typography>
                          <Box sx={{ display: "flex", gap: 2, flexWrap: "wrap" }}>
                            {standaloneAttachments.map((att) => {
                              const isImage = (att.type?.name || att.key || "").match(/image|\.png|\.jpg|\.jpeg|\.gif|\.webp/i);
                              const url = att.url;
                              return (
                                <Box
                                  key={att.id_ || att.key}
                                  sx={{
                                    width: 140,
                                    borderRadius: 2,
                                    overflow: "hidden",
                                    border: "1px solid rgba(148,163,184,0.3)",
                                    background: "#f8fafc",
                                    cursor: isImage && url ? "pointer" : "default",
                                    "&:hover": { boxShadow: "0 6px 18px rgba(15,23,42,0.12)", transform: "translateY(-1px)" },
                                    transition: "box-shadow 200ms ease, transform 200ms ease",
                                  }}
                                  onClick={() => isImage && url && setLightboxUrl(url)}
                                >
                                  {isImage && url ? (
                                    <CardMedia component="img" image={url} alt={att.key} sx={{ height: 100, objectFit: "cover" }} onError={(e) => { e.target.style.display = "none"; }} />
                                  ) : (
                                    <Box sx={{ height: 100, display: "flex", alignItems: "center", justifyContent: "center", bgcolor: "#e2e8f0" }}>
                                      <Typography variant="caption" sx={{ color: "#64748b" }}>{att.type?.name || "File"}</Typography>
                                    </Box>
                                  )}
                                  <Box sx={{ p: 0.8 }}>
                                    <Typography variant="caption" sx={{ color: "#475569", fontSize: "0.68rem", wordBreak: "break-all", display: "block" }}>
                                      {(att.key || "").split("/").pop()}
                                    </Typography>
                                  </Box>
                                </Box>
                              );
                            })}
                          </Box>
                        </CardContent>
                      </Card>
                    )}
                  </Box>
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
