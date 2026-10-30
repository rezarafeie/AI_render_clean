import React from "react";
import { initializeTheme } from "./theme";
import { AppFeatures } from "./local/AppFeatures";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Navigate, Route, Routes, useLocation, useParams } from "react-router-dom";
import { isAuthenticated, restoreSession } from "./auth";
import { AuthProvider, useAuth } from "./auth/AuthContext";
import { JobCacheProvider } from "./JobCache";
import Login from "./Login";
import EditorShell from "./EditorShell";
import { loaders } from "./routeLoaders";
import { LoadingState, ToastHost } from "./ui";
import "./styles/tokens.css";
import "./styles/base.css";
import "./styles/components.css";
import "./styles/shell.css";
import "./styles/studio.css";
import "./styles/auth.css";
import "./styles/pages.css";
import "./styles/legacy.css";

const Studio = React.lazy(loaders.studio);
const Projects = React.lazy(loaders.projects);
const Templates = React.lazy(loaders.templates);
const Settings = React.lazy(() => import("./Settings"));
const AIModels = React.lazy(() => import("./AIModels"));
const Render = React.lazy(() => import("./Render"));
const MyEffects = React.lazy(() => import("./MyEffects"));
const StyleLibrary = React.lazy(() => import("./StyleLibrary"));
const StyleLearner = React.lazy(() => import("./StyleLearner"));
const Library = React.lazy(() => import("./Library"));
const ContentCreator = React.lazy(() => import("./ContentCreator"));
const Localize = React.lazy(() => import("./Localize"));
const TalkingReels = React.lazy(() => import("./TalkingReels"));
const Landing = React.lazy(() => import("./Landing"));
const Signup = React.lazy(() => import("./Signup"));
const ForgotPassword = React.lazy(() => import("./ForgotPassword"));
const ResetPassword = React.lazy(() => import("./ResetPassword"));
const HermesLayout = React.lazy(loaders.hermesLayout);
const HermesPostEditor = React.lazy(loaders.hermesPost);
const HermesHome = React.lazy(loaders.hermesHome);
const HermesChat = React.lazy(loaders.hermesChat);
const HermesContent = React.lazy(loaders.hermesContent);
const HermesAnalytics = React.lazy(loaders.hermesAnalytics);
const HermesFrame = React.lazy(loaders.hermesFrame);
// The OAuth callback lands on /hermes/connect; keep its query so Settings can confirm the connection.
function ReturnToSettings() { const { search } = useLocation(); return <Navigate to={`/settings${search}#integrations`} replace/>; }

function LoadingSpinner() { return <div className="boot" role="status" aria-label="Loading EditorGPT"><span className="spinner"/></div>; }

function GuestRoute({ children }: { children: React.ReactNode }) {
  const { authenticated } = useAuth();
  return authenticated ? <Navigate to="/studio" replace/> : <>{children}</>;
}

class AppErrorBoundary extends React.Component<React.PropsWithChildren, { hasError: boolean }> {
  state = { hasError: false };
  static getDerivedStateFromError() { return { hasError: true }; }
  componentDidCatch(error: Error, info: React.ErrorInfo) { console.error("Unhandled React error", error, info); }
  render() { return this.state.hasError ? <main className="empty boot" role="alert"><strong>Something went wrong</strong><p>Your work is saved. Reload to reconnect.</p><button className="btn" onClick={() => location.reload()}>Reload</button></main> : this.props.children; }
}

function SessionBootstrap({ children }: { children: React.ReactNode }) {
  const [ready, setReady] = React.useState(isAuthenticated());
  React.useEffect(() => { if (!ready) void restoreSession().finally(() => setReady(true)); }, [ready]);
  return ready ? <>{children}</> : <LoadingSpinner/>;
}

function RequireAuth({ children }: { children: React.ReactNode }) {
  const location = useLocation();
  const { authenticated } = useAuth();
  return authenticated ? <>{children}</> : <Navigate to="/login" replace state={{ from: location.pathname + location.search }}/>;
}

function LegacyJobRedirect() {
  const { id = "" } = useParams();
  return <Navigate to={`/studio?legacy=motion:${encodeURIComponent(id)}`} replace/>;
}

function App() {
  return <BrowserRouter><AppFeatures/><AppErrorBoundary><SessionBootstrap><AuthProvider><JobCacheProvider><React.Suspense fallback={<LoadingSpinner/>}><Routes>
    <Route path="/login" element={<GuestRoute><Login/></GuestRoute>}/>
    <Route path="/signup" element={<GuestRoute><Signup/></GuestRoute>}/>
    <Route path="/forgot-password" element={<ForgotPassword/>}/><Route path="/reset-password" element={<ResetPassword/>}/>
    <Route path="/welcome" element={<Landing/>}/>
    <Route element={<EditorShell/>}>
      <Route index element={<Navigate to="/studio" replace/>}/><Route path="studio/:conversationId?" element={<Studio/>}/>
      <Route path="projects" element={<RequireAuth><Projects/></RequireAuth>}/><Route path="templates" element={<Templates/>}/><Route path="settings" element={<RequireAuth><Settings/></RequireAuth>}/>
      <Route path="settings/ai" element={<RequireAuth><AIModels/></RequireAuth>}/>
      <Route path="new" element={<Navigate to="/studio" replace/>}/><Route path="content" element={<RequireAuth><ContentCreator/></RequireAuth>}/><Route path="localize" element={<RequireAuth><Localize/></RequireAuth>}/><Route path="talking" element={<RequireAuth><TalkingReels/></RequireAuth>}/>
      <Route path="jobs" element={<Navigate to="/projects" replace/>}/><Route path="jobs/:id" element={<RequireAuth><LegacyJobRedirect/></RequireAuth>}/><Route path="jobs/:id/render" element={<RequireAuth><Render/></RequireAuth>}/>
      <Route path="my-effects" element={<RequireAuth><MyEffects/></RequireAuth>}/><Route path="library" element={<RequireAuth><Library/></RequireAuth>}/><Route path="style-library" element={<RequireAuth><StyleLibrary/></RequireAuth>}/><Route path="style-learner" element={<RequireAuth><StyleLearner/></RequireAuth>}/><Route path="fonts" element={<Navigate to="/style-library#fonts" replace/>}/>
      <Route path="hermes" element={<RequireAuth><HermesLayout/></RequireAuth>}><Route index element={<HermesHome/>}/><Route path="chat/:chatId" element={<HermesChat/>}/><Route element={<HermesFrame/>}><Route path="content" element={<HermesContent/>}/><Route path="analytics" element={<HermesAnalytics/>}/><Route path="settings" element={<Navigate to="/settings#integrations" replace/>}/><Route path="post/new" element={<HermesPostEditor/>}/><Route path="post/:id" element={<HermesPostEditor/>}/></Route><Route path="connect" element={<ReturnToSettings/>}/><Route path="scheduler" element={<Navigate to="/hermes/content" replace/>}/><Route path="content-plan" element={<Navigate to="/hermes/content" replace/>}/><Route path="advisor" element={<Navigate to="/hermes" replace/>}/><Route path="overview" element={<Navigate to="/hermes" replace/>}/></Route>
      <Route path="*" element={<Navigate to="/studio" replace/>}/>
    </Route>
  </Routes></React.Suspense><ToastHost/></JobCacheProvider></AuthProvider></SessionBootstrap></AppErrorBoundary></BrowserRouter>;
}

initializeTheme();
createRoot(document.getElementById("root")!).render(<App/>);
