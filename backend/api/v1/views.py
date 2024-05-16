from django.contrib.auth import get_user_model
from django.http import Http404, HttpResponse
from django.template.loader import render_to_string
from django_filters.rest_framework import DjangoFilterBackend
from djoser.views import UserViewSet
from recipes.models import (Ingredients, Recipe_Favorite, Recipes,
                            Shopping_Cart, Tags)
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.filters import SearchFilter
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet, ReadOnlyModelViewSet
from users.models import Subscription, UserCustom

from .filters import RecipeFilter
from .pagination import CustomPagination
from .permissions import RecipePermission
from .serializers import (FavoriteCreate, IngredientsSerializer,
                          RecipeCreateSerializer, RecipeReadSerializer,
                          ShoppingCreateSerializer, ShortRecipeRead,
                          Subscribe_GET_Serializer, SubscribeCreateSerializer,
                          TagsSerializer)

User = get_user_model()


class TagViewSet(ReadOnlyModelViewSet):
    queryset = Tags.objects.all()
    serializer_class = TagsSerializer
    pagination_class = None


class IngredientsViewSet(ReadOnlyModelViewSet):
    queryset = Ingredients.objects.all()
    serializer_class = IngredientsSerializer
    pagination_class = None
    filter_backends = (SearchFilter,)
    search_fields = ('^name',)


class CustomUserViewSet(UserViewSet):
    pagination_class = CustomPagination

    @action(detail=False, url_path='subscriptions',
            serializer_class=Subscribe_GET_Serializer)
    def get_subscriptions(self, request):
        subs_id_queryset = request.user.follow.values("follow")
        subs_id_list = [dict_id['follow'] for dict_id in subs_id_queryset]
        queryset = UserCustom.objects.filter(pk__in=subs_id_list)
        page = self.paginate_queryset(queryset)
        serializer = self.get_serializer(page, many=True)
        return self.get_paginated_response(serializer.data)

    @action(detail=True, methods=['post', 'delete'],
            url_path='subscribe', serializer_class=SubscribeCreateSerializer,
            permission_classes=[IsAuthenticated])
    def post_del_subscriptions(self, request, id):
        try:
            user = UserCustom.objects.get(pk=id)
        except User.DoesNotExist:
            raise Http404
        if request.method == 'POST':
            serializer = self.get_serializer(data={'follow': id})
            serializer.is_valid(raise_exception=True)
            serializer.save()
            return Response(
                Subscribe_GET_Serializer(
                    user, context={'request': request}
                ).data,
                status=status.HTTP_201_CREATED,
            )
        object_sub = Subscription.objects.filter(user=request.user, follow=id)
        if object_sub:
            object_sub.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        return Response(
            data={'errors': 'Вы не были подписаны на этого пользователя!'},
            status=status.HTTP_400_BAD_REQUEST
        )


class RecipesViewSet(ModelViewSet):
    filter_backends = (DjangoFilterBackend,)
    filterset_class = RecipeFilter
    permission_classes = (RecipePermission,)

    def get_queryset(self):
        query_params = self.request.query_params
        user = self.request.user
        if query_params.get('is_favorited'):
            try:
                return user.favorite_recipes.all()
            except AttributeError:
                return None
        if query_params.get('is_in_shopping_cart'):
            try:
                return user.recipe_in_shopping_cart.all()
            except AttributeError:
                return None
        return Recipes.objects.all()

    def get_serializer_class(self):
        if self.request.method == 'GET':
            return RecipeReadSerializer
        else:
            return RecipeCreateSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        recipe = self.perform_create(serializer)
        return Response(
            RecipeReadSerializer(
                recipe, context={'request': request}
            ).data, status=status.HTTP_201_CREATED
        )

    def perform_create(self, serializer):
        return serializer.save(author=self.request.user)

    def partial_update(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(
            instance, data=request.data,
        )
        serializer.is_valid(raise_exception=True)
        new_recipe = self.perform_update(serializer)
        return Response(
            RecipeReadSerializer(
                new_recipe, context={'request': request}
            ).data, status=status.HTTP_200_OK
        )

    def perform_update(self, serializer):
        return serializer.save()

    @action(detail=True, methods=['post', 'delete'], url_path='favorite',)
    def post_del_favorite(self, request, pk):
        if request.method == 'POST':
            serializer = FavoriteCreate(
                data={'recipes': pk}, context={'request': request}
            )
            serializer.is_valid(raise_exception=True)
            serializer.save()
            recipe = Recipes.objects.get(pk=pk)
            return Response(
                ShortRecipeRead(recipe).data,
                status=status.HTTP_201_CREATED
            )
        try:
            Recipes.objects.get(pk=pk)
        except Recipes.DoesNotExist:
            raise Http404
        object_fav = Recipe_Favorite.objects.filter(
            users=request.user, recipes=pk
        )
        if object_fav:
            object_fav.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        return Response(
            data={'errors': 'Такого рецепта нет в избранном!'},
            status=status.HTTP_400_BAD_REQUEST
        )

    @action(detail=True, methods=['post', 'delete'], url_path='shopping_cart')
    def post_del_shopping_cart(self, request, pk):
        if request.method == 'POST':
            serializer = ShoppingCreateSerializer(
                data={'recipes': pk}, context={'request': request}
            )
            serializer.is_valid(raise_exception=True)
            serializer.save()
            recipe = Recipes.objects.get(pk=pk)
            return Response(
                ShortRecipeRead(recipe).data,
                status=status.HTTP_201_CREATED
            )
        try:
            Recipes.objects.get(pk=pk)
        except Recipes.DoesNotExist:
            raise Http404
        object_shop = Shopping_Cart.objects.filter(
            users=request.user, recipes=pk
        )
        if object_shop:
            object_shop.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        return Response(
            data={'errors': 'Такого рецепта нет в списке покупок!'},
            status=status.HTTP_400_BAD_REQUEST
        )

    @action(detail=False, methods=['get'], url_path='download_shopping_cart')
    def get_shopping_cart(self, request):
        union_ing = dict()
        recipes_in_shopping_cart = request.user.recipe_in_shopping_cart.all()
        for recipe in recipes_in_shopping_cart:
            ingredients_for_recipe = recipe.ingredients_amount.values(
                'amount', 'ingredients__name', 'ingredients__measurement_unit'
            )
            for ingredient in ingredients_for_recipe:
                ingredient = ingredient['ingredients__name']
                amount = ingredient['amount']
                measurement_unit = ingredient['ingredients__measurement_unit']
                if ingredient in union_ing:
                    union_ing[ingredient] = {
                        'name': ingredient,
                        'amount': union_ing[ingredient]['amount'] + amount,
                        'measurement_unit': measurement_unit
                    }
                else:
                    union_ing[ingredient] = {
                        'name': ingredient,
                        'amount': amount,
                        'measurement_unit': measurement_unit
                    }
        context = {'ingredients': union_ing.values()}
        shopping_cart = render_to_string(
            'shopping_cart.html', context=context
        )
        response = HttpResponse(content_type='text/html')
        header = 'attachment; filename="shopping_cart.html"'
        response['Content-Disposition'] = header
        response.write(shopping_cart)
        return response
