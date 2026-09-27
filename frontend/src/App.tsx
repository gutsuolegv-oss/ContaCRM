import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createBrowserRouter, Navigate, Outlet, RouterProvider } from "react-router";

import { AuthProvider } from "./auth/AuthContext";
import { isEditor, useAuth, useMe } from "./auth/useAuth";
import { Layout } from "./components/Layout";
import { ChangePasswordPage } from "./pages/ChangePasswordPage";
import { ClassifierPage } from "./pages/ClassifierPage";
import { ClientPage } from "./pages/ClientPage";
import { ClientsPage } from "./pages/ClientsPage";
import { DebtsPage } from "./pages/DebtsPage";
import { GridPage } from "./pages/GridPage";
import { LoginPage } from "./pages/LoginPage";
import { NewClientPage } from "./pages/NewClientPage";
import { NotFound } from "./pages/NotFound";
import { SettingsPage } from "./pages/SettingsPage";
import { UsersPage } from "./pages/UsersPage";

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false } },
});

/** Poarta: login → (parola de schimbat) → aplicația. */
function Gate() {
  const { user } = useAuth();
  if (user === undefined) return <div className="loading">Se încarcă…</div>;
  if (user === null) return <LoginPage />;
  if (user.must_change_password) return <ChangePasswordPage />;
  return <Outlet />;
}

/** Paginile de configurare: doar admin și director; contabilul ajunge la lista de clienți. */
function EditorOnly() {
  const me = useMe();
  return isEditor(me) ? <Outlet /> : <Navigate to="/clienti" replace />;
}

const router = createBrowserRouter([
  {
    element: <Gate />,
    children: [
      {
        element: <Layout />,
        children: [
          { index: true, element: <Navigate to="/clienti" replace /> },
          { path: "clienti", element: <ClientsPage /> },
          { path: "clienti/nou", element: <NewClientPage /> },
          { path: "clienti/:id", element: <ClientPage /> },
          { path: "grila", element: <GridPage /> },
          {
            element: <EditorOnly />,
            children: [
              { path: "clasificator", element: <ClassifierPage /> },
              { path: "utilizatori", element: <UsersPage /> },
              { path: "setari", element: <SettingsPage /> },
              { path: "restante", element: <DebtsPage /> },
            ],
          },
          { path: "*", element: <NotFound /> },
        ],
      },
    ],
  },
]);

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <RouterProvider router={router} />
      </AuthProvider>
    </QueryClientProvider>
  );
}
