# Copyright (c) David Berlioz
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""XMP sidecar read/write — pure stdlib (xml.etree.ElementTree).

Sidecar naming convention: ``filename.ext.xmp``
"""

import os
import xml.etree.ElementTree as ET

# XMP namespaces
NS_X = "adobe:ns:meta/"
NS_RDF = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
NS_DC = "http://purl.org/dc/elements/1.1/"
NS_XMP = "http://ns.adobe.com/xap/1.0/"

# Register prefixes for clean serialization
ET.register_namespace("x", NS_X)
ET.register_namespace("rdf", NS_RDF)
ET.register_namespace("dc", NS_DC)
ET.register_namespace("xmp", NS_XMP)


def sidecar_path(image_path):
    """Return the XMP sidecar path for an image file."""
    return image_path + ".xmp"


def read_xmp(image_path):
    """Read metadata from an XMP sidecar file.

    Args:
        image_path: Path to the image file (sidecar is ``image_path.xmp``).

    Returns:
        dict with keys: title, description, keywords (list), creator, rating.
        Returns empty dict if no sidecar exists.
    """
    xmp_path = sidecar_path(image_path)
    if not os.path.isfile(xmp_path):
        return {}

    try:
        tree = ET.parse(xmp_path)
    except ET.ParseError:
        return {}

    root = tree.getroot()
    desc = root.find(".//{%s}Description" % NS_RDF)
    if desc is None:
        return {}

    meta = {}

    # dc:title — Alt bag
    title_el = desc.find("{%s}title" % NS_DC)
    if title_el is not None:
        li = title_el.find(".//{%s}li" % NS_RDF)
        if li is not None and li.text:
            meta["title"] = li.text

    # dc:description — Alt bag
    desc_el = desc.find("{%s}description" % NS_DC)
    if desc_el is not None:
        li = desc_el.find(".//{%s}li" % NS_RDF)
        if li is not None and li.text:
            meta["description"] = li.text

    # dc:subject — Bag of keywords
    subj_el = desc.find("{%s}subject" % NS_DC)
    if subj_el is not None:
        keywords = []
        for li in subj_el.findall(".//{%s}li" % NS_RDF):
            if li.text:
                keywords.append(li.text)
        if keywords:
            meta["keywords"] = keywords

    # dc:creator — Seq
    creator_el = desc.find("{%s}creator" % NS_DC)
    if creator_el is not None:
        li = creator_el.find(".//{%s}li" % NS_RDF)
        if li is not None and li.text:
            meta["creator"] = li.text

    # xmp:Rating — attribute or element
    rating = desc.get("{%s}Rating" % NS_XMP)
    if rating is None:
        rating_el = desc.find("{%s}Rating" % NS_XMP)
        if rating_el is not None:
            rating = rating_el.text
    if rating is not None:
        try:
            meta["rating"] = int(rating)
        except (ValueError, TypeError):
            pass

    return meta


def write_xmp(image_path, meta_dict):
    """Create or update an XMP sidecar file.

    Args:
        image_path: Path to the image file.
        meta_dict: dict with optional keys: title, description, keywords, creator, rating.
    """
    xmp_path = sidecar_path(image_path)

    # Build XMP document
    xmpmeta = ET.Element("{%s}xmpmeta" % NS_X)
    rdf = ET.SubElement(xmpmeta, "{%s}RDF" % NS_RDF)
    desc = ET.SubElement(rdf, "{%s}Description" % NS_RDF)
    desc.set("{%s}about" % NS_RDF, "")

    # dc:title
    title = meta_dict.get("title")
    if title:
        title_el = ET.SubElement(desc, "{%s}title" % NS_DC)
        alt = ET.SubElement(title_el, "{%s}Alt" % NS_RDF)
        li = ET.SubElement(alt, "{%s}li" % NS_RDF)
        li.set("{%s}lang" % "http://www.w3.org/XML/1998/namespace", "x-default")
        li.text = title

    # dc:description
    description = meta_dict.get("description")
    if description:
        desc_el = ET.SubElement(desc, "{%s}description" % NS_DC)
        alt = ET.SubElement(desc_el, "{%s}Alt" % NS_RDF)
        li = ET.SubElement(alt, "{%s}li" % NS_RDF)
        li.set("{%s}lang" % "http://www.w3.org/XML/1998/namespace", "x-default")
        li.text = description

    # dc:subject (keywords)
    keywords = meta_dict.get("keywords")
    if keywords:
        subj_el = ET.SubElement(desc, "{%s}subject" % NS_DC)
        bag = ET.SubElement(subj_el, "{%s}Bag" % NS_RDF)
        for kw in keywords:
            li = ET.SubElement(bag, "{%s}li" % NS_RDF)
            li.text = kw

    # dc:creator
    creator = meta_dict.get("creator")
    if creator:
        creator_el = ET.SubElement(desc, "{%s}creator" % NS_DC)
        seq = ET.SubElement(creator_el, "{%s}Seq" % NS_RDF)
        li = ET.SubElement(seq, "{%s}li" % NS_RDF)
        li.text = creator

    # xmp:Rating
    rating = meta_dict.get("rating")
    if rating is not None:
        desc.set("{%s}Rating" % NS_XMP, str(int(rating)))

    tree = ET.ElementTree(xmpmeta)
    ET.indent(tree, space="  ")
    tree.write(xmp_path, xml_declaration=True, encoding="utf-8")
