/** Lazy route chunks, loadable ahead of time so switching between the editor and Instagram GPT never waits on the network. */
export const loaders = {
  studio: () => import("./Studio"),
  projects: () => import("./Jobs"),
  templates: () => import("./Templates"),
  hermesLayout: () => import("./pages/hermes/HermesLayout.jsx"),
  hermesHome: () => import("./pages/hermes/HermesHome.jsx"),
  hermesChat: () => import("./pages/hermes/HermesChat.jsx"),
  hermesFrame: () => import("./pages/hermes/HermesFrame.jsx"),
  hermesContent: () => import("./pages/hermes/HermesContent.jsx"),
  hermesAnalytics: () => import("./pages/hermes/HermesAnalytics.jsx"),
  hermesPost: () => import("./pages/hermes/HermesPostEditor.jsx"),
};

const settle = (list: (() => Promise<unknown>)[]) => Promise.all(list.map(load => load().catch(() => undefined))).then(() => undefined);

export const preloadHermes = () => settle([loaders.hermesLayout, loaders.hermesHome, loaders.hermesChat, loaders.hermesFrame, loaders.hermesContent, loaders.hermesAnalytics]);
export const preloadEditor = () => settle([loaders.studio, loaders.projects, loaders.templates]);
