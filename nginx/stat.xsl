<?xml version="1.0" encoding="utf-8" ?>
<xsl:stylesheet version="1.0" xmlns:xsl="http://www.w3.org/1999/XSL/Transform">
<xsl:output method="html"/>
<xsl:template match="/">
<!DOCTYPE html>
<html>
<head>
    <title>RTMP Statistics</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; background: #1a1a1a; color: #fff; }
        h1 { color: #00d4ff; }
        table { border-collapse: collapse; width: 100%; margin-top: 20px; }
        th { background: #333; padding: 10px; text-align: left; }
        td { padding: 10px; border-bottom: 1px solid #333; }
        .live { color: #00ff88; font-weight: bold; }
    </style>
</head>
<body>
    <h1>RTMP Statistics</h1>
    <p>Server uptime: <xsl:value-of select="/rtmp/uptime"/> seconds</p>
    
    <h2>Active Streams</h2>
    <table>
        <tr>
            <th>Application</th>
            <th>Stream</th>
            <th>Time</th>
            <th>Bandwidth In</th>
            <th>Bandwidth Out</th>
            <th>Clients</th>
        </tr>
        <xsl:for-each select="/rtmp/server/application">
            <xsl:for-each select="live/stream">
                <tr>
                    <td><xsl:value-of select="../../name"/></td>
                    <td class="live"><xsl:value-of select="name"/></td>
                    <td><xsl:value-of select="time"/> ms</td>
                    <td><xsl:value-of select="bw_in"/> bps</td>
                    <td><xsl:value-of select="bw_out"/> bps</td>
                    <td><xsl:value-of select="nclients"/></td>
                </tr>
            </xsl:for-each>
        </xsl:for-each>
    </table>
</body>
</html>
</xsl:template>
</xsl:stylesheet>
