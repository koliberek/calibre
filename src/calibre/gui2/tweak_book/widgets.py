#!/usr/bin/env python
# vim:fileencoding=utf-8
from __future__ import (unicode_literals, division, absolute_import,
                        print_function)

__license__ = 'GPL v3'
__copyright__ = '2014, Kovid Goyal <kovid at kovidgoyal.net>'

import os
from itertools import izip
from collections import OrderedDict

from PyQt4.Qt import (
    QDialog, QDialogButtonBox, QGridLayout, QLabel, QLineEdit, QVBoxLayout,
    QFormLayout, QHBoxLayout, QToolButton, QIcon, QApplication, Qt, QWidget,
    QPoint, QSizePolicy, QPainter, QStaticText, pyqtSignal, QTextOption,
    QAbstractListModel, QModelIndex, QVariant, QStyledItemDelegate, QStyle,
    QListView, QTextDocument, QSize, QComboBox, QFrame)

from calibre import prepare_string_for_xml
from calibre.gui2 import error_dialog, choose_files, choose_save_file, NONE, info_dialog
from calibre.gui2.tweak_book import tprefs
from calibre.utils.icu import primary_sort_key, sort_key
from calibre.utils.matcher import get_char, Matcher

ROOT = QModelIndex()

class Dialog(QDialog):

    def __init__(self, title, name, parent=None):
        QDialog.__init__(self, parent)
        self.setWindowTitle(title)
        self.name = name
        self.bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.bb.accepted.connect(self.accept)
        self.bb.rejected.connect(self.reject)

        self.setup_ui()

        self.resize(self.sizeHint())
        geom = tprefs.get(name + '-geometry', None)
        if geom is not None:
            self.restoreGeometry(geom)
        if hasattr(self, 'splitter'):
            state = tprefs.get(name + '-splitter-state', None)
            if state is not None:
                self.splitter.restoreState(state)

    def accept(self):
        tprefs.set(self.name + '-geometry', bytearray(self.saveGeometry()))
        if hasattr(self, 'splitter'):
            tprefs.set(self.name + '-splitter-state', bytearray(self.splitter.saveState()))
        QDialog.accept(self)

    def reject(self):
        tprefs.set(self.name + '-geometry', bytearray(self.saveGeometry()))
        if hasattr(self, 'splitter'):
            tprefs.set(self.name + '-splitter-state', bytearray(self.splitter.saveState()))
        QDialog.reject(self)

    def setup_ui(self):
        raise NotImplementedError('You must implement this method in Dialog subclasses')

class RationalizeFolders(Dialog):  # {{{

    TYPE_MAP = (
                ('text', _('Text (HTML) files')),
                ('style', _('Style (CSS) files')),
                ('image', _('Images')),
                ('font', _('Fonts')),
                ('audio', _('Audio')),
                ('video', _('Video')),
                ('opf', _('OPF file (metadata)')),
                ('toc', _('Table of contents file (NCX)')),
    )

    def __init__(self, parent=None):
        Dialog.__init__(self, _('Arrange in folders'), 'rationalize-folders', parent=parent)

    def setup_ui(self):
        self.l = l = QGridLayout()
        self.setLayout(l)

        self.la = la = QLabel(_(
            'Arrange the files in this book into sub-folders based on their types.'
            ' If you leave a folder blank, the files will be placed in the root.'))
        la.setWordWrap(True)
        l.addWidget(la, 0, 0, 1, -1)

        folders = tprefs['folders_for_types']
        for i, (typ, text) in enumerate(self.TYPE_MAP):
            la = QLabel('&' + text)
            setattr(self, '%s_label' % typ, la)
            le = QLineEdit(self)
            setattr(self, '%s_folder' % typ, le)
            val = folders.get(typ, '')
            if val and not val.endswith('/'):
                val += '/'
            le.setText(val)
            la.setBuddy(le)
            l.addWidget(la, i + 1, 0)
            l.addWidget(le, i + 1, 1)
        self.la2 = la = QLabel(_(
            'Note that this will only arrange files inside the book,'
            ' it will not affect how they are displayed in the Files Browser'))
        la.setWordWrap(True)
        l.addWidget(la, i + 2, 0, 1, -1)
        l.addWidget(self.bb, i + 3, 0, 1, -1)

    @property
    def folder_map(self):
        ans = {}
        for typ, x in self.TYPE_MAP:
            val = unicode(getattr(self, '%s_folder' % typ).text()).strip().strip('/')
            ans[typ] = val
        return ans

    def accept(self):
        tprefs['folders_for_types'] = self.folder_map
        return Dialog.accept(self)
# }}}

class MultiSplit(Dialog):  # {{{

    def __init__(self, parent=None):
        Dialog.__init__(self, _('Specify locations to split at'), 'multisplit-xpath', parent=parent)

    def setup_ui(self):
        from calibre.gui2.convert.xpath_wizard import XPathEdit
        self.l = l = QVBoxLayout(self)
        self.setLayout(l)

        self.la = la = QLabel(_(
            'Specify the locations to split at, using an XPath expression (click'
            ' the wizard button for help with generating XPath expressions).'))
        la.setWordWrap(True)
        l.addWidget(la)

        self._xpath = xp = XPathEdit(self)
        xp.set_msg(_('&XPath expression:'))
        xp.setObjectName('editor-multisplit-xpath-edit')
        l.addWidget(xp)
        l.addWidget(self.bb)

    def accept(self):
        if not self._xpath.check():
            return error_dialog(self, _('Invalid XPath expression'), _(
                'The XPath expression %s is invalid.') % self.xpath)
        return Dialog.accept(self)

    @property
    def xpath(self):
        return self._xpath.xpath

# }}}

class ImportForeign(Dialog):  # {{{

    def __init__(self, parent=None):
        Dialog.__init__(self, _('Choose file to import'), 'import-foreign')

    def sizeHint(self):
        ans = Dialog.sizeHint(self)
        ans.setWidth(ans.width() + 200)
        return ans

    def setup_ui(self):
        self.l = l = QFormLayout(self)
        self.setLayout(l)

        la = self.la = QLabel(_(
            'You can import an HTML or DOCX file directly as an EPUB and edit it. The EPUB'
            ' will be generated with minimal changes from the source, unlike doing a full'
            ' conversion in calibre.'))
        la.setWordWrap(True)
        l.addRow(la)

        self.h1 = h1 = QHBoxLayout()
        self.src = src = QLineEdit(self)
        src.setPlaceholderText(_('Choose the file to import'))
        h1.addWidget(src)
        self.b1 = b = QToolButton(self)
        b.setIcon(QIcon(I('document_open.png')))
        b.setText(_('Choose file'))
        h1.addWidget(b)
        l.addRow(_('Source file'), h1)
        b.clicked.connect(self.choose_source)
        b.setFocus(Qt.OtherFocusReason)

        self.h2 = h1 = QHBoxLayout()
        self.dest = src = QLineEdit(self)
        src.setPlaceholderText(_('Choose the location for the newly created EPUB'))
        h1.addWidget(src)
        self.b2 = b = QToolButton(self)
        b.setIcon(QIcon(I('document_open.png')))
        b.setText(_('Choose file'))
        h1.addWidget(b)
        l.addRow(_('Destination file'), h1)
        b.clicked.connect(self.choose_destination)

        l.addRow(self.bb)

    def choose_source(self):
        from calibre.ebooks.oeb.polish.import_book import IMPORTABLE
        path = choose_files(self, 'edit-book-choose-file-to-import', _('Choose file'), filters=[
            (_('Importable files'), list(IMPORTABLE))], select_only_single_file=True)
        if path:
            self.set_src(path[0])

    def set_src(self, path):
        self.src.setText(path)
        self.dest.setText(self.data[1])

    def choose_destination(self):
        path = choose_save_file(self, 'edit-book-destination-for-generated-epub', _('Choose destination'), filters=[
            (_('EPUB files'), ['epub'])], all_files=False)
        if path:
            if not path.lower().endswith('.epub'):
                path += '.epub'
            self.dest.setText(path)

    def accept(self):
        if not unicode(self.src.text()):
            return error_dialog(self, _('Need document'), _(
                'You must specify the source file that will be imported.'), show=True)
        Dialog.accept(self)

    @property
    def data(self):
        src = unicode(self.src.text()).strip()
        dest = unicode(self.dest.text()).strip()
        if not dest:
            dest = src.rpartition('.')[0] + '.epub'
        return src, dest
# }}}

# Quick Open {{{

def make_highlighted_text(emph, text, positions):
    positions = sorted(set(positions) - {-1}, reverse=True)
    text = prepare_string_for_xml(text)
    for p in positions:
        ch = get_char(text, p)
        text = '%s<span style="%s">%s</span>%s' % (text[:p], emph, ch, text[p+len(ch):])
    return text


class Results(QWidget):

    EMPH = "color:magenta; font-weight:bold"
    MARGIN = 4

    item_selected = pyqtSignal()

    def __init__(self, parent=None):
        QWidget.__init__(self, parent=parent)

        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.results = ()
        self.current_result = -1
        self.max_result = -1
        self.mouse_hover_result = -1
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.NoFocus)
        self.text_option = to = QTextOption()
        to.setWrapMode(to.NoWrap)
        self.divider = QStaticText('\xa0→ \xa0')
        self.divider.setTextFormat(Qt.PlainText)

    def item_from_y(self, y):
        if not self.results:
            return
        delta = self.results[0][0].size().height() + self.MARGIN
        maxy = self.height()
        pos = 0
        for i, r in enumerate(self.results):
            bottom = pos + delta
            if pos <= y < bottom:
                return i
                break
            pos = bottom
            if pos > min(y, maxy):
                break
        return -1

    def mouseMoveEvent(self, ev):
        y = ev.pos().y()
        prev = self.mouse_hover_result
        self.mouse_hover_result = self.item_from_y(y)
        if prev != self.mouse_hover_result:
            self.update()

    def mousePressEvent(self, ev):
        if ev.button() == 1:
            i = self.item_from_y(ev.pos().y())
            if i != -1:
                ev.accept()
                self.current_result = i
                self.update()
                self.item_selected.emit()
                return
        return QWidget.mousePressEvent(self, ev)

    def change_current(self, delta=1):
        if not self.results:
            return
        nc = self.current_result + delta
        if 0 <= nc <= self.max_result:
            self.current_result = nc
            self.update()

    def __call__(self, results):
        if results:
            self.current_result = 0
            prefixes = [QStaticText('<b>%s</b>' % os.path.basename(x)) for x in results]
            [(p.setTextFormat(Qt.RichText), p.setTextOption(self.text_option)) for p in prefixes]
            self.maxwidth = max([x.size().width() for x in prefixes])
            self.results = tuple((prefix, self.make_text(text, positions), text)
                for prefix, (text, positions) in izip(prefixes, results.iteritems()))
        else:
            self.results = ()
            self.current_result = -1
        self.max_result = min(10, len(self.results) - 1)
        self.mouse_hover_result = -1
        self.update()

    def make_text(self, text, positions):
        text = QStaticText(make_highlighted_text(self.EMPH, text, positions))
        text.setTextOption(self.text_option)
        text.setTextFormat(Qt.RichText)
        return text

    def paintEvent(self, ev):
        offset = QPoint(0, 0)
        p = QPainter(self)
        p.setClipRect(ev.rect())
        bottom = self.rect().bottom()

        if self.results:
            for i, (prefix, full, text) in enumerate(self.results):
                size = prefix.size()
                if offset.y() + size.height() > bottom:
                    break
                self.max_result = i
                offset.setX(0)
                if i in (self.current_result, self.mouse_hover_result):
                    p.save()
                    if i != self.current_result:
                        p.setPen(Qt.DotLine)
                    p.drawLine(offset, QPoint(self.width(), offset.y()))
                    p.restore()
                offset.setY(offset.y() + self.MARGIN // 2)
                p.drawStaticText(offset, prefix)
                offset.setX(self.maxwidth + 5)
                p.drawStaticText(offset, self.divider)
                offset.setX(offset.x() + self.divider.size().width())
                p.drawStaticText(offset, full)
                offset.setY(offset.y() + size.height() + self.MARGIN // 2)
                if i in (self.current_result, self.mouse_hover_result):
                    offset.setX(0)
                    p.save()
                    if i != self.current_result:
                        p.setPen(Qt.DotLine)
                    p.drawLine(offset, QPoint(self.width(), offset.y()))
                    p.restore()
        else:
            p.drawText(self.rect(), Qt.AlignCenter, _('No results found'))

        p.end()

    @property
    def selected_result(self):
        try:
            return self.results[self.current_result][-1]
        except IndexError:
            pass

class QuickOpen(Dialog):

    def __init__(self, items, parent=None):
        self.matcher = Matcher(items)
        self.matches = ()
        self.selected_result = None
        Dialog.__init__(self, _('Choose file to edit'), 'quick-open', parent=parent)

    def sizeHint(self):
        ans = Dialog.sizeHint(self)
        ans.setWidth(800)
        ans.setHeight(max(600, ans.height()))
        return ans

    def setup_ui(self):
        self.l = l = QVBoxLayout(self)
        self.setLayout(l)

        self.text = t = QLineEdit(self)
        t.textEdited.connect(self.update_matches)
        l.addWidget(t, alignment=Qt.AlignTop)

        example = '<pre>{0}i{1}mages/{0}c{1}hapter1/{0}s{1}cene{0}3{1}.jpg</pre>'.format(
            '<span style="%s">' % Results.EMPH, '</span>')
        chars = '<pre style="%s">ics3</pre>' % Results.EMPH

        self.help_label = hl = QLabel(_(
            '''<p>Quickly choose a file by typing in just a few characters from the file name into the field above.
        For example, if want to choose the file:
        {example}
        Simply type in the characters:
        {chars}
        and press Enter.''').format(example=example, chars=chars))
        hl.setMargin(50), hl.setAlignment(Qt.AlignTop | Qt.AlignHCenter)
        l.addWidget(hl)
        self.results = Results(self)
        self.results.setVisible(False)
        self.results.item_selected.connect(self.accept)
        l.addWidget(self.results)

        l.addWidget(self.bb, alignment=Qt.AlignBottom)

    def update_matches(self, text):
        text = unicode(text).strip()
        self.help_label.setVisible(False)
        self.results.setVisible(True)
        matches = self.matcher(text, limit=100)
        self.results(matches)
        self.matches = tuple(matches)

    def keyPressEvent(self, ev):
        if ev.key() in (Qt.Key_Up, Qt.Key_Down):
            ev.accept()
            self.results.change_current(delta=-1 if ev.key() == Qt.Key_Up else 1)
            return
        return Dialog.keyPressEvent(self, ev)

    def accept(self):
        self.selected_result = self.results.selected_result
        return Dialog.accept(self)

    @classmethod
    def test(cls):
        import os
        from calibre.utils.matcher import get_items_from_dir
        items = get_items_from_dir(os.getcwdu(), lambda x:not x.endswith('.pyc'))
        d = cls(items)
        d.exec_()
        print (d.selected_result)

# }}}

# Filterable names list {{{

class NamesDelegate(QStyledItemDelegate):

    def sizeHint(self, option, index):
        ans = QStyledItemDelegate.sizeHint(self, option, index)
        ans.setHeight(ans.height() + 10)
        return ans

    def paint(self, painter, option, index):
        QStyledItemDelegate.paint(self, painter, option, index)
        text, positions = index.data(Qt.UserRole).toPyObject()
        self.initStyleOption(option, index)
        painter.save()
        painter.setFont(option.font)
        p = option.palette
        c = p.HighlightedText if option.state & QStyle.State_Selected else p.Text
        group = (p.Active if option.state & QStyle.State_Active else p.Inactive)
        c = p.color(group, c)
        painter.setClipRect(option.rect)
        if positions is None or -1 in positions:
            painter.setPen(c)
            painter.drawText(option.rect, Qt.AlignLeft | Qt.AlignVCenter | Qt.TextSingleLine, text)
        else:
            to = QTextOption()
            to.setWrapMode(to.NoWrap)
            to.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            positions = sorted(set(positions) - {-1}, reverse=True)
            text = '<body>%s</body>' % make_highlighted_text(Results.EMPH, text, positions)
            doc = QTextDocument()
            c = 'rgb(%d, %d, %d)'%c.getRgb()[:3]
            doc.setDefaultStyleSheet(' body { color: %s }'%c)
            doc.setHtml(text)
            doc.setDefaultFont(option.font)
            doc.setDocumentMargin(0.0)
            doc.setDefaultTextOption(to)
            height = doc.size().height()
            painter.translate(option.rect.left(), option.rect.top() + (max(0, option.rect.height() - height) // 2))
            doc.drawContents(painter)
        painter.restore()

class NamesModel(QAbstractListModel):

    filtered = pyqtSignal(object)

    def __init__(self, names, parent=None):
        self.items = []
        QAbstractListModel.__init__(self, parent)
        self.set_names(names)

    def set_names(self, names):
        self.names = names
        self.matcher = Matcher(names)
        self.filter('')

    def rowCount(self, parent=ROOT):
        return len(self.items)

    def data(self, index, role):
        if role == Qt.UserRole:
            return QVariant(self.items[index.row()])
        if role == Qt.DisplayRole:
            return QVariant('\xa0' * 20)
        return NONE

    def filter(self, query):
        query = unicode(query or '')
        if not query:
            self.items = tuple((text, None) for text in self.names)
        else:
            self.items = tuple(self.matcher(query).iteritems())
        self.reset()
        self.filtered.emit(not bool(query))

    def find_name(self, name):
        for i, (text, positions) in enumerate(self.items):
            if text == name:
                return i

def create_filterable_names_list(names, filter_text=None, parent=None):
    nl = QListView(parent)
    nl.m = m = NamesModel(names, parent=nl)
    m.filtered.connect(lambda all_items: nl.scrollTo(m.index(0)))
    nl.setModel(m)
    nl.d = NamesDelegate(nl)
    nl.setItemDelegate(nl.d)
    f = QLineEdit(parent)
    f.setPlaceholderText(filter_text or '')
    f.textEdited.connect(m.filter)
    return nl, f

# }}}

# Insert Link {{{
class InsertLink(Dialog):

    def __init__(self, container, source_name, initial_text=None, parent=None):
        self.container = container
        self.source_name = source_name
        self.initial_text = initial_text
        Dialog.__init__(self, _('Insert Hyperlink'), 'insert-hyperlink', parent=parent)
        self.anchor_cache = {}

    def sizeHint(self):
        return QSize(800, 600)

    def setup_ui(self):
        self.l = l = QVBoxLayout(self)
        self.setLayout(l)

        self.h = h = QHBoxLayout()
        l.addLayout(h)

        names = [n for n, linear in self.container.spine_names]
        fn, f = create_filterable_names_list(names, filter_text=_('Filter files'), parent=self)
        self.file_names, self.file_names_filter = fn, f
        fn.selectionModel().selectionChanged.connect(self.selected_file_changed)
        self.fnl = fnl = QVBoxLayout()
        self.la1 = la = QLabel(_('Choose a &file to link to:'))
        la.setBuddy(fn)
        fnl.addWidget(la), fnl.addWidget(f), fnl.addWidget(fn)
        h.addLayout(fnl), h.setStretch(0, 2)

        fn, f = create_filterable_names_list([], filter_text=_('Filter locations'), parent=self)
        self.anchor_names, self.anchor_names_filter = fn, f
        fn.selectionModel().selectionChanged.connect(self.update_target)
        fn.doubleClicked.connect(self.accept, type=Qt.QueuedConnection)
        self.anl = fnl = QVBoxLayout()
        self.la2 = la = QLabel(_('Choose a &location (anchor) in the file:'))
        la.setBuddy(fn)
        fnl.addWidget(la), fnl.addWidget(f), fnl.addWidget(fn)
        h.addLayout(fnl), h.setStretch(1, 1)

        self.tl = tl = QFormLayout()
        self.target = t = QLineEdit(self)
        t.setPlaceholderText(_('The destination (href) for the link'))
        tl.addRow(_('&Target:'), t)
        l.addLayout(tl)

        self.text_edit = t = QLineEdit(self)
        la.setBuddy(t)
        tl.addRow(_('Te&xt:'), t)
        t.setText(self.initial_text or '')
        t.setPlaceholderText(_('The (optional) text for the link'))

        l.addWidget(self.bb)

    def selected_file_changed(self, *args):
        rows = list(self.file_names.selectionModel().selectedRows())
        if not rows:
            self.anchor_names.model().set_names([])
        else:
            name, positions = self.file_names.model().data(rows[0], Qt.UserRole).toPyObject()
            self.populate_anchors(name)

    def populate_anchors(self, name):
        if name not in self.anchor_cache:
            from calibre.ebooks.oeb.base import XHTML_NS
            root = self.container.parsed(name)
            self.anchor_cache[name] = sorted(
                (set(root.xpath('//*/@id')) | set(root.xpath('//h:a/@name', namespaces={'h':XHTML_NS}))) - {''}, key=primary_sort_key)
        self.anchor_names.model().set_names(self.anchor_cache[name])
        self.update_target()

    def update_target(self):
        rows = list(self.file_names.selectionModel().selectedRows())
        if not rows:
            return
        name = self.file_names.model().data(rows[0], Qt.UserRole).toPyObject()[0]
        if name == self.source_name:
            href = ''
        else:
            href = self.container.name_to_href(name, self.source_name)
        frag = ''
        rows = list(self.anchor_names.selectionModel().selectedRows())
        if rows:
            anchor = self.anchor_names.model().data(rows[0], Qt.UserRole).toPyObject()[0]
            if anchor:
                frag = '#' + anchor
        href += frag
        self.target.setText(href or '#')

    @property
    def href(self):
        return unicode(self.target.text()).strip()

    @property
    def text(self):
        return unicode(self.text_edit.text()).strip()

    @classmethod
    def test(cls):
        import sys
        from calibre.ebooks.oeb.polish.container import get_container
        c = get_container(sys.argv[-1], tweak_mode=True)
        d = cls(c, next(c.spine_names)[0])
        if d.exec_() == d.Accepted:
            print (d.href, d.text)

# }}}

# Insert Semantics {{{

class InsertSemantics(Dialog):

    def __init__(self, container, parent=None):
        self.container = container
        self.anchor_cache = {}
        self.original_type_map = {item.get('type', ''):(container.href_to_name(item.get('href'), container.opf_name), item.get('href', '').partition('#')[-1])
            for item in container.opf_xpath('//opf:guide/opf:reference[@href and @type]')}
        self.final_type_map = self.original_type_map.copy()
        self.create_known_type_map()
        Dialog.__init__(self, _('Set Semantics'), 'insert-semantics', parent=parent)

    def sizeHint(self):
        return QSize(800, 600)

    def create_known_type_map(self):
        _ = lambda x: x
        self.known_type_map = {
            'title-page': _('Title Page'),
            'toc': _('Table of Contents'),
            'index': _('Index'),
            'glossary': _('Glossary'),
            'acknowledgements': _('Acknowledgements'),
            'bibliography': _('Bibliography'),
            'colophon': _('Colophon'),
            'copyright-page': _('Copyright page'),
            'dedication': _('Dedication'),
            'epigraph': _('Epigraph'),
            'foreword': _('Foreword'),
            'loi': _('List of Illustrations'),
            'lot': _('List of Tables'),
            'notes:': _('Notes'),
            'preface': _('Preface'),
            'text': _('Text'),
        }
        _ = __builtins__['_']
        type_map_help = {
            'title-page': _('Page with title, author, publisher, etc.'),
            'index': _('Back-of-book style index'),
            'text': _('First "real" page of content'),
        }
        t = _
        all_types = [(k, (('%s (%s)' % (t(v), type_map_help[k])) if k in type_map_help else t(v))) for k, v in self.known_type_map.iteritems()]
        all_types.sort(key=lambda x: sort_key(x[1]))
        self.all_types = OrderedDict(all_types)

    def setup_ui(self):
        self.l = l = QVBoxLayout(self)
        self.setLayout(l)

        self.tl = tl = QFormLayout()
        self.semantic_type = QComboBox(self)
        for key, val in self.all_types.iteritems():
            self.semantic_type.addItem(val, key)
        tl.addRow(_('Type of &semantics:'), self.semantic_type)
        self.target = t = QLineEdit(self)
        t.setPlaceholderText(_('The destination (href) for the link'))
        tl.addRow(_('&Target:'), t)
        l.addLayout(tl)

        self.hline = hl = QFrame(self)
        hl.setFrameStyle(hl.HLine)
        l.addWidget(hl)

        self.h = h = QHBoxLayout()
        l.addLayout(h)

        names = [n for n, linear in self.container.spine_names]
        fn, f = create_filterable_names_list(names, filter_text=_('Filter files'), parent=self)
        self.file_names, self.file_names_filter = fn, f
        fn.selectionModel().selectionChanged.connect(self.selected_file_changed)
        self.fnl = fnl = QVBoxLayout()
        self.la1 = la = QLabel(_('Choose a &file:'))
        la.setBuddy(fn)
        fnl.addWidget(la), fnl.addWidget(f), fnl.addWidget(fn)
        h.addLayout(fnl), h.setStretch(0, 2)

        fn, f = create_filterable_names_list([], filter_text=_('Filter locations'), parent=self)
        self.anchor_names, self.anchor_names_filter = fn, f
        fn.selectionModel().selectionChanged.connect(self.update_target)
        fn.doubleClicked.connect(self.accept, type=Qt.QueuedConnection)
        self.anl = fnl = QVBoxLayout()
        self.la2 = la = QLabel(_('Choose a &location (anchor) in the file:'))
        la.setBuddy(fn)
        fnl.addWidget(la), fnl.addWidget(f), fnl.addWidget(fn)
        h.addLayout(fnl), h.setStretch(1, 1)

        self.bb.addButton(self.bb.Help)
        self.bb.helpRequested.connect(self.help_requested)
        l.addWidget(self.bb)
        self.semantic_type_changed()
        self.semantic_type.currentIndexChanged.connect(self.semantic_type_changed)
        self.target.textChanged.connect(self.target_text_changed)

    def help_requested(self):
        d = info_dialog(self, _('About semantics'), _(
            'Semantics refer to additional information about specific locations in the book.'
            ' For example, you can specify that a particular location is the dedication or the preface'
            ' or the table of contents and so on.\n\nFirst choose the type of semantic information, then'
            ' choose a file and optionally a location within the file to point to.\n\nThe'
            ' semantic information will be written in the <guide> section of the opf file.'))
        d.resize(d.sizeHint())
        d.exec_()

    def semantic_type_changed(self):
        item_type = unicode(self.semantic_type.itemData(self.semantic_type.currentIndex()).toString())
        name, frag = self.final_type_map.get(item_type, (None, None))
        self.show_type(name, frag)

    def show_type(self, name, frag):
        self.file_names_filter.clear(), self.anchor_names_filter.clear()
        self.file_names.clearSelection(), self.anchor_names.clearSelection()
        if name is not None:
            row = self.file_names.model().find_name(name)
            if row is not None:
                sm = self.file_names.selectionModel()
                sm.select(self.file_names.model().index(row), sm.ClearAndSelect)
                if frag:
                    row = self.anchor_names.model().find_name(frag)
                    if row is not None:
                        sm = self.anchor_names.selectionModel()
                        sm.select(self.anchor_names.model().index(row), sm.ClearAndSelect)
        self.target.blockSignals(True)
        if name is not None:
            self.target.setText(name + (('#' + frag) if frag else ''))
        else:
            self.target.setText('')
        self.target.blockSignals(False)

    def target_text_changed(self):
        name, frag = unicode(self.target.text()).partition('#')[::2]
        item_type = unicode(self.semantic_type.itemData(self.semantic_type.currentIndex()).toString())
        self.final_type_map[item_type] = (name, frag or None)

    def selected_file_changed(self, *args):
        rows = list(self.file_names.selectionModel().selectedRows())
        if not rows:
            self.anchor_names.model().set_names([])
        else:
            name, positions = self.file_names.model().data(rows[0], Qt.UserRole).toPyObject()
            self.populate_anchors(name)

    def populate_anchors(self, name):
        if name not in self.anchor_cache:
            from calibre.ebooks.oeb.base import XHTML_NS
            root = self.container.parsed(name)
            self.anchor_cache[name] = sorted(
                (set(root.xpath('//*/@id')) | set(root.xpath('//h:a/@name', namespaces={'h':XHTML_NS}))) - {''}, key=primary_sort_key)
        self.anchor_names.model().set_names(self.anchor_cache[name])
        self.update_target()

    def update_target(self):
        rows = list(self.file_names.selectionModel().selectedRows())
        if not rows:
            return
        name = self.file_names.model().data(rows[0], Qt.UserRole).toPyObject()[0]
        href = name
        frag = ''
        rows = list(self.anchor_names.selectionModel().selectedRows())
        if rows:
            anchor = self.anchor_names.model().data(rows[0], Qt.UserRole).toPyObject()[0]
            if anchor:
                frag = '#' + anchor
        href += frag
        self.target.setText(href or '#')

    @property
    def changed_type_map(self):
        return {k:v for k, v in self.final_type_map.iteritems() if v != self.original_type_map.get(k, None)}

    def apply_changes(self, container):
        from calibre.ebooks.oeb.polish.opf import set_guide_item, get_book_language
        from calibre.translations.dynamic import translate
        lang = get_book_language(container)
        for item_type, (name, frag) in self.changed_type_map.iteritems():
            title = self.known_type_map[item_type]
            if lang:
                title = translate(lang, title)
            set_guide_item(container, item_type, title, name, frag=frag)

    @classmethod
    def test(cls):
        import sys
        from calibre.ebooks.oeb.polish.container import get_container
        c = get_container(sys.argv[-1], tweak_mode=True)
        d = cls(c)
        if d.exec_() == d.Accepted:
            import pprint
            pprint.pprint(d.changed_type_map)
            d.apply_changes(d.container)

# }}}

if __name__ == '__main__':
    app = QApplication([])
    InsertSemantics.test()
