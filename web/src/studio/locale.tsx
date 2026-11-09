import React from "react";

/** True when the chat is written in Persian: its clocks, durations and numbers are then shown the Persian way. */
export const FaContext = React.createContext(false);
export const useFa = () => React.useContext(FaContext);
