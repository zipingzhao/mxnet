# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.

import functools
import mxnet.ndarray as nd
from mxnet.ndarray import zeros_like
from mxnet.autograd import *
from mxnet.test_utils import *


def grad_and_loss(func, argnum=None):
    """Return function that computes both gradient of arguments and loss value.

    Parameters
    ----------
    func: a python function
        The forward (loss) function.
    argnum: an int or a list of int
        The index of argument to calculate gradient for.

    Returns
    -------
    grad_and_loss_func: a python function
        A function that would compute both the gradient of arguments and loss value.
    """
    @functools.wraps(func)
    def wrapped(*args):
        """Wrapped function."""
        variables = args
        if argnum is not None:
            argnum_ = argnum if isinstance(argnum, list) else [argnum]
            variables = [args[i] for i in argnum_]
        for x in variables:
            assert isinstance(x, NDArray), "type of autograd input should NDArray."
        grads = [zeros_like(x) for x in variables]
        mark_variables(variables, grads)
        with record():
            outputs = func(*args)
        backward([outputs] if isinstance(outputs, NDArray) else outputs)
        return grads, outputs
    return wrapped

def grad(func, argnum=None):
    """Return function that computes gradient of arguments.

    Parameters
    ----------
    func: a python function
        The forward (loss) function.
    argnum: an int or a list of int
        The index of argument to calculate gradient for.

    Returns
    -------
    grad_func: a python function
        A function that would compute the gradient of arguments.

    Examples
    --------
    >>> # autograd supports dynamic graph which is changed
    >>> # every instance
    >>> def func(x):
    >>>     r = random.randint(0, 1)
    >>>     if r % 2:
    >>>         return x**2
    >>>     else:
    >>>         return x/3
    >>> # use `grad(func)` to get the gradient function
    >>> for x in range(10):
    >>>     grad_func = grad(func)
    >>>     inputs = nd.array([[1, 2, 3], [4, 5, 6]])
    >>>     grad_vals = grad_func(inputs)
    """
    grad_with_loss_func = grad_and_loss(func, argnum)
    @functools.wraps(grad_with_loss_func)
    def wrapped(*args):
        return grad_with_loss_func(*args)[0]
    return wrapped

def autograd_assert(*args, **kwargs):
    func   = kwargs["func"]
    grad_f = kwargs["grad_func"]
    argnum = kwargs["argnum"] if 'argnum' in kwargs else None

    grad_func = grad_and_loss(func, argnum)
    grad_vals, output = grad_func(*args)
    res = func(*args)
    assert same(output.asnumpy(), res.asnumpy())
    grad_res = grad_f(*args)
    assert len(grad_vals) == len(grad_res)
    for a, b in zip(grad_vals, grad_res):
        assert same(a.asnumpy(), b.asnumpy())

def test_unary_func():
    x = nd.uniform(shape=(4, 5))
    f_exp         = lambda x: nd.exp(x)
    f_exp_grad    = lambda x: [nd.exp(x)]
    autograd_assert(x, func=f_exp, grad_func=f_exp_grad)
    f_half        = lambda x: x/2
    f_half_grad   = lambda x: [nd.ones(x.shape) * 0.5]
    autograd_assert(x, func=f_half, grad_func=f_half_grad)
    f_square      = lambda x: x**2
    f_square_grad = lambda x: [2*x]
    autograd_assert(x, func=f_square, grad_func=f_square_grad)

def test_binary_func():
    x = nd.uniform(shape=(4, 5))
    y = nd.uniform(shape=(4, 5))
    f_add      = lambda x, y: x+y
    f_add_grad = lambda x, y: [nd.ones(x.shape), nd.ones(y.shape)]
    autograd_assert(x, y, func=f_add, grad_func=f_add_grad)
    f_mul      = lambda x, y: x*y
    f_mul_grad = lambda x, y: [y, x]
    autograd_assert(x, y, func=f_mul, grad_func=f_mul_grad)
    f_compose  = lambda x, y: x+x*y
    f_compose_grad = lambda x, y: [nd.ones(x.shape) + y, x]
    autograd_assert(x, y, func=f_compose, grad_func=f_compose_grad)

def test_operator_with_state():
    def f_fc(a, b, weight, bias):
        x = a*b
        fc = nd.FullyConnected(
            x, weight, bias, num_hidden=32)
        return fc

    a = nd.uniform(shape=(64, 50))
    b = nd.uniform(shape=(64, 50))
    weight = nd.uniform(shape=(32, 50))
    bias = nd.uniform(shape=(32, ))

    grad_func = grad_and_loss(f_fc)
    grad_vals, outputs = grad_func(a, b, weight, bias)
    # (TODO) assert

def test_argnum():
    def f_with_mode(a, b, mode):
        if mode:
            return a+b
        else:
            return a*b

    a = nd.uniform(shape=(3, 2))
    b = nd.uniform(shape=(3, 2))
    f_add_grad = lambda x, y, mode: [nd.ones(x.shape), nd.ones(y.shape)]
    f_mul_grad = lambda x, y, mode: [y, x]
    autograd_assert(a, b, True,
        argnum=[0, 1], func=f_with_mode, grad_func=f_add_grad)
    autograd_assert(a, b, False,
        argnum=[0, 1], func=f_with_mode, grad_func=f_mul_grad)


def test_training():
    x = nd.ones((10, 10))
    with record():
        y = nd.Dropout(x, p=0.5)
        assert not (y.asnumpy() == x.asnumpy()).all()
        with pause():
            y = nd.Dropout(x, p=0.5)
            assert (y.asnumpy() == x.asnumpy()).all()


def test_out_grads():
    x = nd.ones((3, 5))
    dx = nd.zeros_like(x)
    mark_variables([x], [dx])
    da = None
    db = nd.array([1,2,3,4,5])
    dc = nd.array([5,4,3,2,1])

    with record():
        a, b, c = nd.split(x, axis=0, num_outputs=3, squeeze_axis=True)
        backward([a, b, c], [da, db, dc])

    assert (dx.asnumpy() == np.array(
        [[1,1,1,1,1],
         [1,2,3,4,5],
         [5,4,3,2,1]])).all()


def test_detach_updated_grad():
    x = nd.ones((2, 2))
    dx = nd.zeros_like(x)
    y = nd.ones_like(x)
    dy = nd.zeros_like(x)
    mark_variables([x, y], [dx, dy])
    assert x._fresh_grad == False
    assert y._fresh_grad == False

    with record():
        x2 = x + 2
        y2  = x2 + y
        y2.backward()
    assert (dx.asnumpy() == 1).all()
    assert x._fresh_grad == True
    assert y._fresh_grad == True

    dx[:] = 0
    x._fresh_grad = False
    y._fresh_grad = False
    assert x._fresh_grad == False
    assert y._fresh_grad == False
    with record():
        x2 = x + 2
        x2 = x2.detach()
        y2  = x2 + y
        y2.backward()
    assert (dx.asnumpy() == 0).all()
    assert y._fresh_grad == True
    assert x._fresh_grad == False


def test_retain_grad():
    x = mx.nd.ones((2, 2))
    dx = mx.nd.zeros((2, 2))
    mark_variables([x], [dx], grad_reqs='add')
    with record():
        y = x + 1
        y.backward(retain_graph=False)
    assert (dx.asnumpy() == 1).all()

    dx[:] = 0
    with record():
        y = x + 1
        y.backward(retain_graph=True)
        y.backward(retain_graph=False)
    assert (dx.asnumpy() == 2).all()

    # The following sequence should throw an exception. We discard the expected
    # stderr stack trace output for this operation to keep the test logs clean.
    with discard_stderr():
        try:
            with record():
                y = x + 1
                y.backward()
                y.backward()
        except Exception:
            return

    raise AssertionError(
        "differentiating the same graph twice without retain_graph should fail")


def test_attach_grad():
    x = mx.nd.zeros((10,))
    assert x.grad is None
    x.attach_grad()
    with record():
        y = x * 2
        assert y.grad is None
        y.backward()
    assert (x.grad.asnumpy() == 2).all()


def test_is_train():
    x = mx.nd.ones((10, 10))
    x.attach_grad()
    with record(train_mode=True):
        assert is_recording()
        assert is_training()
        y = mx.nd.Dropout(x, p=0.5)
        assert y.asnumpy().max() == 2 and y.asnumpy().min() == 0
        y.backward()
        assert (x.grad.asnumpy() == y.asnumpy()).all()

        with predict_mode():
            assert is_recording()
            assert not is_training()
            y = mx.nd.Dropout(x, p=0.5)
            assert (y.asnumpy() == x.asnumpy()).all()
            y.backward(train_mode=False)
            assert (x.grad.asnumpy() == x.asnumpy()).all()

    with record(train_mode=False):
        assert is_recording()
        assert not is_training()
        y = mx.nd.Dropout(x, p=0.5)
        assert (y.asnumpy() == x.asnumpy()).all()
        y.backward(train_mode=False)
        assert (x.grad.asnumpy() == x.asnumpy()).all()

        with train_mode():
            assert is_recording()
            assert is_training()
            y = mx.nd.Dropout(x, p=0.5)
            assert y.asnumpy().max() == 2 and y.asnumpy().min() == 0
            y.backward()
            assert (x.grad.asnumpy() == y.asnumpy()).all()

    assert not is_recording()
    assert not is_training()
    y = mx.nd.Dropout(x, p=0.5)
    assert (y.asnumpy() == x.asnumpy()).all()

    with train_mode():
        assert not is_recording()
        assert is_training()
        y = mx.nd.Dropout(x, p=0.5)
        assert y.asnumpy().max() == 2 and y.asnumpy().min() == 0


def test_function():
    class func(Function):
        def forward(self, x, y):
            m = x / y
            n = x * y
            self.save_for_backward(x, y)
            return m, n

        def backward(self, dm, dn):
            x, y = self.saved_tensors
            dx = dm/y + dn*y
            dy = dn*x - dm * x / y / y
            return dx, dy

    f = func()
    x = mx.nd.random_uniform(shape=(10,))
    x.attach_grad()
    y = mx.nd.random_uniform(shape=(10,))
    y.attach_grad()
    with record():
        m, n = f(x, y)
        backward([m, n])

    dx1 = x.grad.asnumpy()
    dy1 = y.grad.asnumpy()

    with record():
        backward([x/y, x*y])

    assert_almost_equal(x.grad.asnumpy(), dx1)
    assert_almost_equal(y.grad.asnumpy(), dy1)


def test_get_symbol():
    x = mx.nd.ones((1,))
    x.attach_grad()
    with record():
        y = x*x + 2*x - 1
    assert len(get_symbol(y).list_arguments()) == 1

    z = mx.nd.ones((1,))
    z.attach_grad()
    with record():
        y = x*x + 2*z - 1
    assert len(get_symbol(y).list_arguments()) == 2


if __name__ == "__main__":
    import nose
    nose.runmodule()