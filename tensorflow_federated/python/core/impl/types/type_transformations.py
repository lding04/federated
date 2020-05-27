# Copyright 2018, The TensorFlow Federated Authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# limitations under the License.
"""A library of transformation functions for computation types."""

from typing import Any, Callable, Tuple, TypeVar

from tensorflow_federated.python.common_libs import anonymous_tuple
from tensorflow_federated.python.common_libs import py_typecheck
from tensorflow_federated.python.core.api import computation_types

T = TypeVar('T')


# TODO(b/134525440): Unifying the recursive methods in type_analysis.
def transform_type_postorder(
    type_signature: computation_types.Type,
    transform_fn: Callable[[computation_types.Type],
                           Tuple[computation_types.Type, bool]]):
  """Walks type tree of `type_signature` postorder, calling `transform_fn`.

  Args:
    type_signature: Instance of `computation_types.Type` to transform
      recursively.
    transform_fn: Transformation function to apply to each node in the type tree
      of `type_signature`. Must be instance of Python function type.

  Returns:
    A possibly transformed version of `type_signature`, with each node in its
    tree the result of applying `transform_fn` to the corresponding node in
    `type_signature`.

  Raises:
    TypeError: If the types don't match the specification above.
  """
  py_typecheck.check_type(type_signature, computation_types.Type)
  py_typecheck.check_callable(transform_fn)
  if isinstance(type_signature, computation_types.FederatedType):
    transformed_member, member_mutated = transform_type_postorder(
        type_signature.member, transform_fn)
    if member_mutated:
      type_signature = computation_types.FederatedType(transformed_member,
                                                       type_signature.placement,
                                                       type_signature.all_equal)
    type_signature, type_signature_mutated = transform_fn(type_signature)
    return type_signature, type_signature_mutated or member_mutated
  elif isinstance(type_signature, computation_types.SequenceType):
    transformed_element, element_mutated = transform_type_postorder(
        type_signature.element, transform_fn)
    if element_mutated:
      type_signature = computation_types.SequenceType(transformed_element)
    type_signature, type_signature_mutated = transform_fn(type_signature)
    return type_signature, type_signature_mutated or element_mutated
  elif isinstance(type_signature, computation_types.FunctionType):
    if type_signature.parameter is not None:
      transformed_parameter, parameter_mutated = transform_type_postorder(
          type_signature.parameter, transform_fn)
    else:
      transformed_parameter, parameter_mutated = (None, False)
    transformed_result, result_mutated = transform_type_postorder(
        type_signature.result, transform_fn)
    if parameter_mutated or result_mutated:
      type_signature = computation_types.FunctionType(transformed_parameter,
                                                      transformed_result)
    type_signature, type_signature_mutated = transform_fn(type_signature)
    return type_signature, (
        type_signature_mutated or parameter_mutated or result_mutated)
  elif isinstance(type_signature, computation_types.NamedTupleType):
    elements = []
    elements_mutated = False
    for element in anonymous_tuple.iter_elements(type_signature):
      transformed_element, element_mutated = transform_type_postorder(
          element[1], transform_fn)
      elements_mutated = elements_mutated or element_mutated
      elements.append((element[0], transformed_element))
    if elements_mutated:
      if isinstance(type_signature,
                    computation_types.NamedTupleTypeWithPyContainerType):
        container_type = computation_types.NamedTupleTypeWithPyContainerType.get_container_type(
            type_signature)
        type_signature = computation_types.NamedTupleTypeWithPyContainerType(
            elements, container_type)
      else:
        type_signature = computation_types.NamedTupleType(elements)
    type_signature, type_signature_mutated = transform_fn(type_signature)
    return type_signature, type_signature_mutated or elements_mutated
  elif isinstance(type_signature, (
      computation_types.AbstractType,
      computation_types.PlacementType,
      computation_types.TensorType,
  )):
    return transform_fn(type_signature)


# TODO(b/134525440): Unifying the recursive methods in type_analysis.
def visit_preorder(type_spec: Any, fn: Callable[[Any, T], T], context: T):
  """Recursively calls `fn` on the possibly nested structure `type_spec`.

  Walks the tree in a preorder manner. Updates `context` on the way down with
  the appropriate information, as defined in `fn`.

  Args:
    type_spec: A `computation_types.Type` or object convertible to it by
      `computation_types.to_type`.
    fn: A function to apply to each of the constituent elements of `type_spec`
      with the argument `context`. Must return an updated version of `context`
      which incorporated the information we'd like to track as we move down the
      type tree.
    context: Initial state of information to be passed down the tree.
  """
  type_signature = computation_types.to_type(type_spec)
  context = fn(type_signature, context)
  if isinstance(type_signature, computation_types.FederatedType):
    visit_preorder(type_signature.member, fn, context)
  elif isinstance(type_signature, computation_types.SequenceType):
    visit_preorder(type_signature.element, fn, context)
  elif isinstance(type_signature, computation_types.FunctionType):
    visit_preorder(type_signature.parameter, fn, context)
    visit_preorder(type_signature.result, fn, context)
  elif isinstance(type_signature, computation_types.NamedTupleType):
    for _, element in anonymous_tuple.iter_elements(type_signature):
      visit_preorder(element, fn, context)
