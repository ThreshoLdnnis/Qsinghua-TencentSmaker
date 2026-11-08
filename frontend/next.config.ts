import type { NextConfig } from "next";

const config: NextConfig = {
  output: "standalone",
  agentRules: false,
  devIndicators: false,
  poweredByHeader: false,
};

export default config;
