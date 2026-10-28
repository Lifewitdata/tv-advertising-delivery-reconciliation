"""Execute these pure-Python notebooks without requiring networked kernels."""
import ast
import base64
import contextlib
import io
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import nbformat


def execute(path):
    book=nbformat.read(path,as_version=4)
    namespace={'__name__':'__main__'}
    count=0
    for cell in book.cells:
        if cell.cell_type!='code':continue
        count+=1;cell.execution_count=count;outputs=[];stream=io.StringIO()
        def show(*args,**kwargs):
            for number in plt.get_fignums():
                buffer=io.BytesIO();plt.figure(number).savefig(buffer,format='png',bbox_inches='tight')
                outputs.append(nbformat.v4.new_output('display_data',data={'image/png':base64.b64encode(buffer.getvalue()).decode()}))
            plt.close('all')
        plt.show=show
        tree=ast.parse(cell.source)
        final=tree.body.pop() if tree.body and isinstance(tree.body[-1],ast.Expr) else None
        with contextlib.redirect_stdout(stream),contextlib.redirect_stderr(stream):
            exec(compile(tree,str(path),'exec'),namespace)
            result=eval(compile(ast.Expression(final.value),str(path),'eval'),namespace) if final else None
        if stream.getvalue():outputs.insert(0,nbformat.v4.new_output('stream',name='stdout',text=stream.getvalue()))
        if result is not None:outputs.append(nbformat.v4.new_output('execute_result',execution_count=count,data={'text/plain':repr(result)}))
        cell.outputs=outputs
    nbformat.validate(book);nbformat.write(book,path)
    print(f'{path.name}: {count} cells executed without errors')


if __name__=='__main__':
    for path in sorted(Path('notebooks').glob('*.ipynb')):execute(path)
