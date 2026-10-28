import { createContext, useContext } from 'react';

// The layout shares the agent's state and a few actions with every Hermes page.
export const HermesContext = createContext({ agent: null, reloadAgent: async () => {}, runAgent: async () => {}, openAgent: () => {}, connected: null });
export const useHermes = () => useContext(HermesContext);
