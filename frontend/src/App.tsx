import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createBrowserRouter, Navigate, Outlet, RouterProvider } from "react-router";

import { AuthProvider } from "./auth/AuthContext";
import { useAuth } from "./auth/useAuth";
import { Layout } from "./components/Layout";
import { ChangePasswordPage } from "./pages/ChangePasswordPage";
import { ClientPage } from "./pages/ClientPage";
import { ClientsPage } from "./pages/ClientsPage";
import { LoginPage } from "./pages/LoginPage";
import { NewClientPage } from "./pages/NewClientPage";
import { Placeholder } from "./pages/Placeholder";

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
          { path: "grila", element: <Placeholder title="Grila lunii" /> },
          { path: "clasificator", element: <Placeholder title="Clasificator" /> },
          { path: "utilizatori", element: <Placeholder title="Utilizatori" /> },
          { path: "*", element: <Placeholder title="Pagina nu există" /> },
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
