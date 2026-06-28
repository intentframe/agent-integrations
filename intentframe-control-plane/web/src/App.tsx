import { Route, Routes } from "react-router-dom";
import { Layout } from "./components/Layout";
import OverviewPage from "./pages/Overview";
import GovernancePage from "./pages/Governance";
import PolicyPage from "./pages/Policy";
import AuditPage from "./pages/Audit";

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<OverviewPage />} />
        <Route path="governance" element={<GovernancePage />} />
        <Route path="policy" element={<PolicyPage />} />
        <Route path="audit" element={<AuditPage />} />
      </Route>
    </Routes>
  );
}
