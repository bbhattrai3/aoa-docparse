import { useAuth0 } from "@auth0/auth0-react";
import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import api, { setAuthToken } from "../services/api";

export default function InvitationPage() {
  const { token } = useParams<{ token: string }>();
  const { isAuthenticated, loginWithRedirect, getAccessTokenSilently } = useAuth0();
  const navigate = useNavigate();
  const [message, setMessage] = useState("Checking invitation…");

  useEffect(() => {
    if (!token) return;
    if (!isAuthenticated) {
      loginWithRedirect({ appState: { returnTo: `/invite/${token}` } });
      return;
    }
    (async () => {
      try {
        const accessToken = await getAccessTokenSilently();
        setAuthToken(accessToken);
        const response = await api.post(`/account/invitations/${token}/accept`);
        navigate(`/dashboard/${response.data.parish_id}`, { replace: true });
      } catch (error: any) {
        setMessage(error?.response?.data?.detail || "This invitation could not be accepted.");
      }
    })();
  }, [token, isAuthenticated, loginWithRedirect, getAccessTokenSilently, navigate]);

  return <div className="min-h-screen flex items-center justify-center bg-stone-50 text-stone-600">{message}</div>;
}
