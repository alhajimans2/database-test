exports.handler = async (event) => {
  try {
    const backendUrl = process.env.BACKEND_URL || "https://tit-database-app.onrender.com";
    if (!backendUrl) {
      return {
        statusCode: 500,
        headers: { "content-type": "text/plain; charset=utf-8" },
        body: "BACKEND_URL is not configured in Netlify environment variables.",
      };
    }

    const backendBase = backendUrl.endsWith("/") ? backendUrl.slice(0, -1) : backendUrl;

    const functionPrefix = "/.netlify/functions/proxy";
    const incomingPath = event.path.startsWith(functionPrefix)
      ? event.path.slice(functionPrefix.length)
      : event.path;
    const targetPath = incomingPath && incomingPath.length > 0 ? incomingPath : "/";
    const query = event.rawQuery ? `?${event.rawQuery}` : "";
    const targetUrl = `${backendBase}${targetPath}${query}`;

    const requestHeaders = { ...event.headers };
    delete requestHeaders.host;
    delete requestHeaders["x-forwarded-host"];
    delete requestHeaders["x-nf-request-id"];
    requestHeaders["x-forwarded-proto"] = "https";

    const response = await fetch(targetUrl, {
      method: event.httpMethod,
      headers: requestHeaders,
      body: ["GET", "HEAD"].includes(event.httpMethod) ? undefined : event.body,
      redirect: "manual",
    });

    const responseHeaders = {};
    response.headers.forEach((value, key) => {
      const lower = key.toLowerCase();
      if (["content-encoding", "transfer-encoding", "connection"].includes(lower)) {
        return;
      }
      responseHeaders[key] = value;
    });

    const body = await response.text();

    return {
      statusCode: response.status,
      headers: responseHeaders,
      body,
    };
  } catch (error) {
    return {
      statusCode: 502,
      headers: { "content-type": "text/plain; charset=utf-8" },
      body: `Proxy error: ${error.message}`,
    };
  }
};
