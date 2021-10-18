import re
import os
import json
import inspect
from pathlib import Path
import xml.etree.ElementTree as etree
from xml.etree.ElementTree import parse as parse_xml
from markdown.inlinepatterns import InlineProcessor
from markdown.blockprocessors import BlockProcessor
from markdown.extensions import Extension


docs_path = Path(__file__).parent.parent / "docs"


def etree_fontawesome(icon, group="fas"):
    el = etree.Element("i")
    el.attrib["class"] = "%s fa-%s" % (group, icon)
    return el


def clean_link(filename):
    if not filename.startswith("/") and not filename.startswith("."):
        filename = "../" + filename
    return filename


def css_style(**args):
    string = ""
    for k, v in args.items():
        string += "%s:%s;" % (k.replace("_", "-"), v)

    return string


class LottieRenderer:
    _id = 0

    @staticmethod
    def render(*, parent: etree.Element = None, url=None, json_data=None, download_file=None, width=None, height=None):
        element = etree.Element("div")

        if parent is not None:
            parent.append(element)

        animation = etree.SubElement(element, "div")
        animation.attrib["class"] = "alpha_checkered"
        animation.attrib["id"] = "lottie_target_%s" % LottieRenderer._id

        if width:
            animation.attrib["style"] = "width:%spx;height:%spx" % (width, height)

        play = etree.Element("button")
        element.append(play)
        play.attrib["id"] = "lottie_play_{id}".format(id=LottieRenderer._id)
        play.attrib["onclick"] = (
            "anim_{id}.play(); " +
            "document.getElementById('lottie_pause_{id}').style.display = 'inline-block'; " +
            "this.style.display = 'none'"
        ).format(id=LottieRenderer._id)
        play.append(etree_fontawesome("play"))
        play.attrib["title"] = "Play"
        play.attrib["style"] = "display:none"

        pause = etree.Element("button")
        element.append(pause)
        pause.attrib["id"] = "lottie_pause_{id}".format(id=LottieRenderer._id)
        pause.attrib["onclick"] = (
            "anim_{id}.pause(); " +
            "document.getElementById('lottie_play_{id}').style.display = 'inline-block'; " +
            "this.style.display = 'none'"
        ).format(id=LottieRenderer._id)
        pause.append(etree_fontawesome("pause"))
        pause.attrib["title"] = "Pause"

        if download_file:
            download = etree.Element("a")
            element.append(download)
            download.attrib["href"] = download_file
            if download_file.endswith("rawr"):
                download.attrib["download"] = ""
            download.attrib["title"] = "Download"
            download_button = etree.Element("button")
            download.append(download_button)
            download_button.append(etree_fontawesome("download"))

        script = etree.Element("script")
        element.append(script)

        if json_data is None:
            script.text = """
                var anim_{id} = bodymovin.loadAnimation({{
                    container: document.getElementById('lottie_target_{id}'),
                    renderer: 'svg',
                    loop: true,
                    autoplay: true,
                    path: '{file}'
                }});
            """.format(id=LottieRenderer._id, file=url)
        else:
            script.text = """
                var lottie_json_{id} = {json_data};

                var anim_{id} = null;

                function reload_lottie_{id}()
                {{
                    var animData = {{
                        container: document.getElementById('lottie_target_{id}'),
                        renderer: 'svg',
                        loop: true,
                        autoplay: true,
                        animationData: lottie_json_{id}
                    }};
                    if ( anim_{id} != null )
                        anim_{id} = anim_{id}.destroy();
                    anim_{id} = bodymovin.loadAnimation(animData);
                }}

                reload_lottie_{id}();
            """.format(id=LottieRenderer._id, json_data=json.dumps(json_data))

        id = LottieRenderer._id
        LottieRenderer._id += 1

        return (element, id)


class LottieInlineProcessor(InlineProcessor):
    def __init__(self, md):
        pattern = r'{lottie:([^:]+)(?::([0-9]+):([0-9]+))}'
        super().__init__(pattern, md)

    def handleMatch(self, m, data):
        filename = "examples/" + m.group(1)
        download_file = filename
        lottie_url = "../" + filename

        element = LottieRenderer.render(
            url=lottie_url,
            download_file=download_file,
            width=m.group(2),
            height=m.group(3)
        )[0]

        return element, m.start(0), m.end(0)


class LottieColor(InlineProcessor):
    def __init__(self, pattern, md, mult):
        super().__init__(pattern, md)
        self.mult = mult

    def handleMatch(self, match, data):
        span = etree.Element("span")
        span.attrib["style"] = "font-family: right"

        comp = [float(match.group(i)) / self.mult for i in range(2, 5)]

        hex = "#" + "".join("%02x" % round(x * 255) for x in comp)
        color = etree.SubElement(span, "span")
        color.attrib["style"] = css_style(
            width="24px",
            height="24px",
            background_color=hex,
            border="1px solid black",
            display="inline-block",
            vertical_align="middle",
            margin_right="0.5ex"
        )

        etree.SubElement(span, "code").text = "[%s]" % ", ".join("%.3g" % x for x in comp)

        return span, match.start(0), match.end(0)


class Matrix(BlockProcessor):
    RE_FENCE_START = r'^\s*\{matrix\}\s*\n'

    def test(self, parent, block):
        return re.match(self.RE_FENCE_START, block)

    def run(self, parent, blocks):
        table = etree.SubElement(parent, "table")
        table.attrib["style"] = "font-family: monospace; text-align: center; background-color: #fcfdff; border: 1px solid #ccc;"
        table.attrib["class"] = "table-plain"
        rows = blocks.pop(0)
        for row in rows.split("\n")[1:]:
            tr = etree.SubElement(table, "tr")
            for cell in row.split():
                td = etree.SubElement(tr, "td")
                td.text = cell
                td.attrib["style"] = "width: 25%;"
        return True


class SchemaData:
    _data = None

    @classmethod
    def get_schema(cls):
        if cls._data is None:
            with open(docs_path / "schema" / "lottie.schema.json") as file:
                cls._data = json.load(file)
        return cls._data

    def get_ref(self, ref: str):
        return self.get_path(ref.strip("#").strip("/").split("/"))

    def get_path(self, path):
        schema = self.get_schema()
        for chunk in path:
            schema = schema[chunk]
        return schema

    def get_enum_values(self, name):
        enum = self.get_path(["constants", name])
        data = []
        for item in enum["oneOf"]:
            data.append((item["const"], item["title"], item.get("description", "")))
        return data


class SchemaEnum(BlockProcessor):
    re_fence_start = re.compile(r'^\s*\{schema_enum:([^}]+)\}\s*(?:\n|$)')
    re_row = re.compile(r'^\s*(\w+)\s*:\s*(.*)')

    def test(self, parent, block):
        return self.re_fence_start.match(block)

    def run(self, parent, blocks):
        name = self.test(parent, blocks[0]).group(1)

        enum_data = SchemaData().get_enum_values(name)

        table = etree.SubElement(parent, "table")
        descriptions = {}

        for value, name, description in enum_data:
            if description:
                descriptions[str(value)] = description

        # Override descriptions if specified from markdown
        rows = blocks.pop(0)
        for row in rows.split("\n")[1:]:
            match = self.re_row.match(row)
            if match:
                descriptions[match.group(0)] = match.group(1)

        thead = etree.SubElement(etree.SubElement(table, "thead"), "tr")
        etree.SubElement(thead, "th").text = "Value"
        etree.SubElement(thead, "th").text = "Name"
        if descriptions:
            etree.SubElement(thead, "th").text = "Description"

        tbody = etree.SubElement(table, "tbody")

        for value, name, _ in enum_data:
            tr = etree.SubElement(tbody, "tr")
            etree.SubElement(etree.SubElement(tr, "td"), "code").text = repr(value)
            etree.SubElement(tr, "td").text = name
            if descriptions:
                etree.SubElement(tr, "td").text = descriptions.get(str(value), "")

        return True


class SchemaAttribute(InlineProcessor):
    def __init__(self, md):
        super().__init__(r'\{schema_attribute:(?P<attribute>[^:]+):(?P<path>[^:]+)\}', md)

    def handleMatch(self, match, data):
        span = etree.Element("span")
        span.text = SchemaData().get_ref(match.group("path")).get(match.group("attribute"), "")
        return span, match.start(0), match.end(0)


class LottiePlayground(BlockProcessor):
    re_fence_start = re.compile(r'^\s*\{lottie_playground:([^:]+)(?::([0-9]+):([0-9]+))\}')
    re_row = re.compile(r'^\s*(?P<label>[^:]+)\s*:\s*(?P<type>\w+)\s*:\s*(?P<path>[^:]+)\s*:\s*(?P<args>.*)')

    def test(self, parent, block):
        return self.re_fence_start.match(block)

    def run(self, parent, blocks):
        block = blocks.pop(0)
        match = self.test(parent, block)

        with open(docs_path / "examples" / match.group(1)) as file:
            json_data = json.load(file)

        element, anim_id = LottieRenderer.render(
            parent=parent,
            json_data=json_data,
            width=match.group(2),
            height=match.group(3)
        )

        for index, line in enumerate(block.strip().split("\n")[1:]):
            row_match = self.re_row.match(line)
            if not row_match:
                continue

            label = row_match.group("label")
            type = row_match.group("type")
            path = row_match.group("path")
            args = row_match.group("args").split(":")

            input_p = etree.Element("p")
            element.insert(index, input_p)
            label_element = etree.SubElement(input_p, "label")
            label_element.text = label
            label_element.tail = " "
            id_base = "playground_{id}_{index}".format(id=anim_id, index=index)

            if type == "enum":
                input = etree.SubElement(input_p, "select")
                input.attrib["onchange"] = "lottie_json_{id}.{path} = event.target.value; reload_lottie_{id}();".format(id=anim_id, path=path)

                for value, title, _ in SchemaData().get_enum_values(args[0]):
                    etree.SubElement(input, "option", {"value": str(value)}).text = title

            elif type == "slider":
                input = etree.SubElement(input_p, "input", {
                    "type": "range",
                    "min": args[0],
                    "value": args[1],
                    "max": args[2],
                    "oninput": inspect.cleandoc("""
                        lottie_json_{id}.{path} = Number(event.target.value);
                        document.getElementById('{span}').innerText = event.target.value;
                        reload_lottie_{id}();
                    """.format(id=anim_id, path=path, span=id_base + "_span"))
                })
                etree.SubElement(input_p, "span", {
                    "id": id_base + "_span"
                }).text = args[1]

            if input is not None:
                input.attrib["autocomplete"] = "off"


class GlaxnimateExtension(Extension):
    def extendMarkdown(self, md):
        md.inlinePatterns.register(LottieInlineProcessor(md), 'lottie', 175)
        md.inlinePatterns.register(LottieColor(r'{lottie_color:(([^,]+),\s*([^,]+),\s*([^,]+))}', md, 1), 'lottie_color', 175)
        md.inlinePatterns.register(LottieColor(r'{lottie_color_255:(([^,]+),\s*([^,]+),\s*([^,]+))}', md, 255), 'lottie_color_255', 175)
        md.parser.blockprocessors.register(Matrix(md.parser), 'matrix', 175)
        md.parser.blockprocessors.register(SchemaEnum(md.parser), 'schema_enum', 175)
        md.inlinePatterns.register(SchemaAttribute(md), 'schema_attribute', 175)
        md.parser.blockprocessors.register(LottiePlayground(md.parser), 'lottie_playground', 175)


def makeExtension(**kwargs):
    return GlaxnimateExtension(**kwargs)

