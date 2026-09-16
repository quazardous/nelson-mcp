<?xml version='1.0' encoding='UTF-8'?>
<description
  xmlns="http://openoffice.org/extensions/description/2006"
  xmlns:dep="http://openoffice.org/extensions/description/2006"
  xmlns:xlink="http://www.w3.org/1999/xlink"
  xmlns:d="http://openoffice.org/extensions/description/2006"
  xmlns:l="http://libreoffice.org/extensions/description/2011">
    <identifier value="org.extension.nelson"/>
    <version value="{{VERSION}}"/>
	<dependencies>
		<!-- Conservative and deliberate. The code's syntax floor is Python 3.6
		     (f-strings), and LibreOffice 6.4 already bundles 3.7 — but nothing
		     older than 26.2 has ever actually been run. Claiming a version we
		     have not exercised is how an extension earns bug reports that are
		     not bugs. Widen this on evidence, not on optimism. -->
		<l:LibreOffice-minimal-version d:name="LibreOffice 7.4" value="7.4"/>
	</dependencies>
    <publisher>
        <name xlink:href="https://github.com/quazardous/nelson-mcp">David Berlioz</name>
    </publisher>
    <display-name>
        <name>Nelson MCP</name>
    </display-name>

    <extension-description>
        <src xlink:href="registration/description_en-US.txt" lang="en"/>
    </extension-description>

  <icon>
  <default xlink:href="assets/logo.png"/>
  </icon>



</description>
