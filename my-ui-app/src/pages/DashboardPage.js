import React, { useState, useEffect } from "react";
import {
  Alert,
  Box,
  Typography,
  Button,
  Card,
  LinearProgress,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
} from "@mui/material";
import {
  BACKEND_API_URL,
  getActiveBackendApiUrl,
  listManagers,
  listOffices,
  listTickets,
} from "../api/backendCrud";

const DashboardPage = ({ onBack }) => {
  const [managers, setManagers] = useState([]);
  const [tickets, setTickets] = useState([]);
  const [businessUnits, setBusinessUnits] = useState([]);
  const [view, setView] = useState("load"); // "load", "managers", "tickets", "businessUnits"
  const [loading, setLoading] = useState(false);
  const [backendError, setBackendError] = useState("");
  const dummyManagerLoads = [
    { managerIndex: 1, load: 22, displayLoad: 22 },
    { managerIndex: 2, load: 38, displayLoad: 38 },
    { managerIndex: 3, load: 67, displayLoad: 67 },
    { managerIndex: 4, load: 73, displayLoad: 73 },
    { managerIndex: 5, load: 91, displayLoad: 91 },
  ];

  const fetchData = async () => {
    setLoading(true);
    setBackendError("");
    const [managersResult, ticketsResult, officesResult] = await Promise.allSettled([
      listManagers({ expand_position: true, expand_city: true, expand_skills: true }),
      listTickets({
        expand: true,
        include_attachments: false,
        include_attachment_type: false,
        include_attachment_url: false,
      }),
      listOffices({ expand_city: true }),
    ]);

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

    if (errors.length) {
      setBackendError(errors.join(" | "));
    }

    setLoading(false);
  };

  // Fetch data from backend
  useEffect(() => {
    fetchData();
  }, []);

  // Handle Analyze button
  const handleAnalyze = async () => {
    await fetchData();
    setView("load");
  };

  const getLoadColor = (load) => {
    if (load >= 70) return "#f44336"; // red
    if (load >= 35) return "#ffeb3b"; // yellow
    return "#4caf50"; // green
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

  const managerLoadRows = managers.length
    ? managers.slice(0, 5).map((manager, index) => {
        const rawLoad = Number(manager.in_progress_requests || 0);
        const normalizedLoad = Math.max(0, Math.min(100, Number.isFinite(rawLoad) ? rawLoad : 0));
        return {
          managerIndex: manager.id_ || index + 1,
          load: normalizedLoad,
          displayLoad: Number.isFinite(rawLoad) ? rawLoad : 0,
        };
      })
    : dummyManagerLoads;

  const managerTableRows = managers.map((manager) => ({
    id: manager.id_,
    position: manager.position?.name || manager.position_id || "-",
    city: manager.city?.name || manager.city_id || "-",
    skills: (manager.skills || []).map((skill) => skill.name).join(", ") || "-",
    inProgress: manager.in_progress_requests ?? 0,
  }));

  const ticketTableRows = tickets.map((ticket) => {
    const addressText = ticket.address
      ? `${ticket.address.street || ""} ${ticket.address.home_number || ""}`.trim()
      : "-";
    return {
      id: ticket.id_,
      segment: ticket.segment?.name || ticket.segment_id || "-",
      gender: ticket.gender?.name || ticket.gender_id || "-",
      dateOfBirth: ticket.date_of_birth || "-",
      address: addressText || "-",
      description: ticket.description || "-",
    };
  });

  const businessUnitRows = businessUnits.map((office) => ({
    id: office.id_,
    city: office.city?.name || office.city_id || "-",
    address: office.address || "-",
  }));

  return (
    <Box
      sx={{
        display: "flex",
        minHeight: "100vh",
        background:
          "radial-gradient(circle at 10% 10%, #e0f2fe 0%, #dbeafe 30%, #ede9fe 60%, #f8fafc 100%)",
      }}
    >
      {/* Main content */}
      <Box sx={{ flex: 1, padding: 4, display: "flex", flexDirection: "column", minHeight: 0 }}>
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
            Loading data from backend ({getActiveBackendApiUrl() || BACKEND_API_URL})...
          </Typography>
        )}

        {!!backendError && (
          <Alert severity="error" sx={{ mb: 2 }}>
            {backendError}
          </Alert>
        )}

        <Box sx={{ flex: 1, minHeight: 0, overflowY: view === "load" ? "hidden" : "auto" }}>
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
              <Box
                sx={{
                  display: "grid",
                  gridTemplateColumns: "1fr 3fr 1fr",
                  gap: 2,
                  borderBottom: "1px solid rgba(148, 163, 184, 0.35)",
                  paddingBottom: 1.5,
                  marginBottom: 2,
                }}
              >
                <Typography variant="h6" sx={{ fontWeight: 800, color: "#1e293b" }}>
                  Manager
                </Typography>
                <Typography variant="h6" sx={{ fontWeight: 800, color: "#1e293b" }}>
                  Load Status
                </Typography>
                <Typography variant="h6" sx={{ fontWeight: 800, color: "#1e293b" }}>
                  Number of Tasks
                </Typography>
              </Box>

              <Box sx={{ overflowY: "auto" }}>
                {managerLoadRows.map((item) => (
                  <Box
                    key={item.managerIndex}
                    sx={{
                      display: "grid",
                      gridTemplateColumns: "1fr 3fr 1fr",
                      gap: 2,
                      alignItems: "center",
                      marginBottom: 2,
                    }}
                  >
                    <Typography variant="body1">{`Manager ${item.managerIndex}`}</Typography>

                    <LinearProgress
                      variant="determinate"
                      value={item.load}
                      sx={{
                        height: 16,
                        borderRadius: 8,
                        backgroundColor: "rgba(148, 163, 184, 0.22)",
                        "& .MuiLinearProgress-bar": {
                          backgroundColor: getLoadColor(item.load),
                          boxShadow: "0 0 12px rgba(37, 99, 235, 0.22)",
                        },
                      }}
                    />

                    <Typography variant="body1" sx={{ textAlign: "right" }}>
                      {item.displayLoad}/100
                    </Typography>
                  </Box>
                ))}
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
                    background:
                      "linear-gradient(120deg, rgba(14,165,233,0.22) 0%, rgba(37,99,235,0.20) 60%, rgba(124,58,237,0.18) 100%)",
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
                      <TableCell>{row.position}</TableCell>
                      <TableCell>{row.city}</TableCell>
                      <TableCell>{row.skills}</TableCell>
                      <TableCell>{row.inProgress}</TableCell>
                    </TableRow>
                  ))
                ) : (
                  <TableRow>
                    <TableCell colSpan={5} align="center">
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
                    background:
                      "linear-gradient(120deg, rgba(14,165,233,0.22) 0%, rgba(37,99,235,0.20) 60%, rgba(124,58,237,0.18) 100%)",
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
                  <TableCell>Gender</TableCell>
                  <TableCell>Date of Birth</TableCell>
                  <TableCell>Address</TableCell>
                  <TableCell>Description</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {ticketTableRows.length > 0 ? (
                  ticketTableRows.map((row) => (
                    <TableRow key={row.id}>
                      <TableCell>{row.id}</TableCell>
                      <TableCell>{row.segment}</TableCell>
                      <TableCell>{row.gender}</TableCell>
                      <TableCell>{row.dateOfBirth}</TableCell>
                      <TableCell>{row.address}</TableCell>
                      <TableCell>{row.description}</TableCell>
                    </TableRow>
                  ))
                ) : (
                  <TableRow>
                    <TableCell colSpan={6} align="center">
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
                    background:
                      "linear-gradient(120deg, rgba(14,165,233,0.22) 0%, rgba(37,99,235,0.20) 60%, rgba(124,58,237,0.18) 100%)",
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
        </Box>
      </Box>

      {/* Sidebar */}
      <Box
        sx={{
          width: 300,
          padding: 2,
          borderLeft: "1px solid rgba(148, 163, 184, 0.35)",
          display: "flex",
          flexDirection: "column",
          justifyContent: "space-between",
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
            sx={sidebarButtonSx(view === "businessUnits")}
            variant={view === "businessUnits" ? "contained" : "outlined"}
            onClick={() => setView("businessUnits")}
          >
            Business Units
          </Button>
        </Box>

        <Button
          variant="contained"
          onClick={handleAnalyze}
          sx={{
            borderRadius: 3,
            minHeight: 52,
            fontWeight: 800,
            letterSpacing: "0.02em",
            background: "linear-gradient(120deg, #ec4899 0%, #db2777 45%, #7e22ce 100%)",
            boxShadow: "0 12px 26px rgba(190, 24, 93, 0.35)",
            "&:hover": {
              background: "linear-gradient(120deg, #db2777 0%, #be185d 45%, #6b21a8 100%)",
              boxShadow: "0 14px 30px rgba(190, 24, 93, 0.4)",
            },
          }}
        >
          Refresh Data
        </Button>
      </Box>
    </Box>
  );
};

export default DashboardPage;
