import { Routes, Route, Navigate } from "react-router-dom";
import Layout from "@/pages/Layout";
import NewspapersList from "@/pages/NewspapersList";
import NewspaperPreview from "@/pages/NewspaperPreview";
import IssueDetails from "@/pages/IssueDetails";
import ConfigsList from "@/pages/ConfigsList";
import ConfigEdit from "@/pages/ConfigEdit";

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<NewspapersList />} />
        <Route path="issues/:id" element={<NewspaperPreview />} />
        <Route path="issues/:id/details" element={<IssueDetails />} />
        <Route path="configs" element={<ConfigsList />} />
        <Route path="configs/new" element={<ConfigEdit />} />
        <Route path="configs/:id" element={<ConfigEdit />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
